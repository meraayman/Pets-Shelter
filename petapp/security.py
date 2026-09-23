"""Passwords, sign-in checks and CSRF protection."""
import secrets
import time
from functools import wraps

from flask import abort, flash, g, redirect, request, session, url_for
from markupsafe import Markup
from werkzeug.security import check_password_hash, generate_password_hash

try:  # only needed to read passwords created by the old PHP version
    import bcrypt
except ImportError:  # pragma: no cover
    bcrypt = None

DEFAULT_ADMIN_PASSWORD = "admin123"


# ---------- passwords ----------
def hash_password(password):
    return generate_password_hash(password)


def is_legacy_hash(stored):
    return bool(stored) and stored.startswith(("$2y$", "$2a$", "$2b$"))


def verify_password(stored, password):
    if not stored or not password:
        return False
    if is_legacy_hash(stored):
        # Hashes made by PHP's password_hash(); bcrypt reads $2y$ as $2b$
        if bcrypt is None:
            return False
        try:
            return bcrypt.checkpw(password.encode("utf-8"), ("$2b$" + stored[4:]).encode("utf-8"))
        except ValueError:
            return False
    try:
        return check_password_hash(stored, password)
    except ValueError:
        return False


# ---------- simple sign-in throttling (per username + IP, in memory) ----------
_failed = {}
MAX_ATTEMPTS = 5
LOCK_SECONDS = 300


def _key(username):
    return f"{(username or '').lower()}|{request.remote_addr}"


def is_locked(username):
    count, until = _failed.get(_key(username), (0, 0))
    return until > time.time()


def register_failure(username):
    k = _key(username)
    count, _ = _failed.get(k, (0, 0))
    count += 1
    _failed[k] = (count, time.time() + LOCK_SECONDS if count >= MAX_ATTEMPTS else 0)


def clear_failures(username):
    _failed.pop(_key(username), None)


# ---------- CSRF ----------
def csrf_token():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(32)
    return session["csrf_token"]


def csrf_field():
    return Markup(f'<input type="hidden" name="csrf_token" value="{csrf_token()}">')


def check_csrf():
    """Called before every POST request."""
    if request.method != "POST":
        return
    sent = request.form.get("csrf_token", "")
    if not sent or not secrets.compare_digest(sent, session.get("csrf_token", "")):
        abort(400, description="This form expired. Go back, reload the page and try again.")


# ---------- access control ----------
def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            flash("Sign in to continue.", "error")
            return redirect(url_for("auth.login", next=request.full_path))
        return view(*args, **kwargs)

    return wrapped


def admin_required(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if g.user["user_type"] != "admin":
            abort(403)
        return view(*args, **kwargs)

    return wrapped
