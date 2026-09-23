"""Staff sign in / sign out."""
from urllib.parse import urlparse

from flask import Blueprint, flash, g, redirect, render_template, request, session, url_for

from .db import execute, query
from .security import (DEFAULT_ADMIN_PASSWORD, clear_failures, hash_password, is_legacy_hash, is_locked,
                       register_failure, verify_password)

bp = Blueprint("auth", __name__)


def _safe_next(target):
    """Only allow redirects back into this site."""
    if not target:
        return None
    parts = urlparse(target)
    if parts.scheme or parts.netloc or not target.startswith("/"):
        return None
    return target


@bp.route("/login", methods=["GET", "POST"])
def login():
    if g.user:
        return redirect(url_for("admin.dashboard"))

    username = ""
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if is_locked(username):
            flash("Too many failed attempts. Wait 5 minutes and try again.", "error")
            return render_template("auth/login.html", username=username)

        user = query("SELECT * FROM tbl_user WHERE username = ?", (username,), one=True)
        if user and verify_password(user["password"], password):
            clear_failures(username)
            # Upgrade passwords saved by the old PHP version to the new format
            if is_legacy_hash(user["password"]):
                execute("UPDATE tbl_user SET password = ? WHERE user_id = ?", (hash_password(password), user["user_id"]))
            session["user_id"] = user["user_id"]
            if password == DEFAULT_ADMIN_PASSWORD:
                flash("You're using the default password. Change it now under My profile.", "error")
            return redirect(_safe_next(request.args.get("next")) or url_for("admin.dashboard"))

        register_failure(username)
        flash("That username and password don't match. Check them and try again.", "error")

    return render_template("auth/login.html", username=username)


@bp.route("/logout", methods=["POST"])
def logout():
    session.pop("user_id", None)
    flash("You've been signed out.", "success")
    return redirect(url_for("public.home"))
