"""Accounts for adopters and pet owners (separate from staff sign-in)."""
import re
import time
from datetime import date
from functools import wraps

from flask import Blueprint, abort, flash, g, redirect, render_template, request, session, url_for

from .db import execute, query, scalar
from .helpers import form_text
from .security import (clear_failures, hash_password, is_legacy_hash, is_locked, register_failure,
                       verify_password)

bp = Blueprint("portal", __name__, url_prefix="/account")

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# Both tables have the same columns with different prefixes
KINDS = {
    "adopter": {"table": "tbl_adopter", "p": "adopter", "label": "Adopter"},
    "owner": {"table": "tbl_pet_owner", "p": "pet_owner", "label": "Pet owner"},
}


def _normalise(kind, row):
    p = KINDS[kind]["p"]
    data = {k.replace(p + "_", ""): v for k, v in dict(row).items()}
    data["kind"] = kind
    return data


def load_member():
    kind, mid = session.get("member_kind"), session.get("member_id")
    if kind not in KINDS or not mid:
        return None
    cfg = KINDS[kind]
    row = query(f"SELECT * FROM {cfg['table']} WHERE {cfg['p']}_id = ?", (mid,), one=True)
    if row is None:
        session.pop("member_kind", None)
        session.pop("member_id", None)
        return None
    return _normalise(kind, row)


def member_required(kind=None):
    def deco(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if g.member is None:
                flash("Sign in to your account to continue.", "error")
                return redirect(url_for("portal.login", next=request.full_path))
            if kind and g.member["kind"] != kind:
                abort(403)
            return view(*args, **kwargs)
        return wrapped
    return deco


# ---------- sign in / register / sign out ----------
@bp.route("/login", methods=["GET", "POST"])
def login():
    if g.member:
        return redirect(url_for("portal.home"))
    kind = request.values.get("kind", "adopter")
    if kind not in KINDS:
        kind = "adopter"
    username = ""
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        throttle_key = f"{kind}:{username}"
        if is_locked(throttle_key):
            flash("Too many failed attempts. Wait 5 minutes and try again.", "error")
        else:
            cfg = KINDS[kind]
            row = query(f"SELECT * FROM {cfg['table']} WHERE lower({cfg['p']}_username) = lower(?)", (username,), one=True)
            stored = row[f"{cfg['p']}_password"] if row else None
            if row and verify_password(stored, password):
                clear_failures(throttle_key)
                if is_legacy_hash(stored):
                    execute(f"UPDATE {cfg['table']} SET {cfg['p']}_password = ? WHERE {cfg['p']}_id = ?",
                            (hash_password(password), row[f"{cfg['p']}_id"]))
                session["member_kind"] = kind
                session["member_id"] = row[f"{cfg['p']}_id"]
                flash(f"Welcome back, {row[cfg['p'] + '_name']}.", "success")
                nxt = request.args.get("next", "")
                return redirect(nxt if nxt.startswith("/") and not nxt.startswith("//") else url_for("portal.home"))
            register_failure(throttle_key)
            flash("That username and password don't match. Check that you picked the right account type.", "error")
    return render_template("portal/login.html", kind=kind, username=username)


@bp.route("/register", methods=["GET", "POST"])
def register():
    if g.member:
        return redirect(url_for("portal.home"))
    form = {"name": "", "email": "", "contact": "", "address": "", "username": ""}
    if request.method == "POST":
        f = request.form
        form = {
            "name": form_text(f, "name", 100),
            "email": form_text(f, "email", 100),
            "contact": form_text(f, "contact", 30),
            "address": form_text(f, "address", 255),
            "username": form_text(f, "username", 50),
        }
        password, confirm = f.get("password", ""), f.get("confirm_password", "")
        errors = []
        if f.get("website"):  # spam trap
            return redirect(url_for("public.home"))
        if time.time() - session.get("register_last", 0) < 30:
            errors.append("Please wait a few seconds before trying again.")
        if not form["name"]:
            errors.append("Enter your full name.")
        if not EMAIL_RE.match(form["email"]):
            errors.append("Enter a valid email address so the shelter can contact you.")
        if not re.match(r"^[A-Za-z0-9_.-]{3,50}$", form["username"]):
            errors.append("Usernames need 3 or more letters, numbers, dots, dashes or underscores.")
        elif scalar("SELECT 1 FROM tbl_adopter WHERE lower(adopter_username) = lower(?)", (form["username"],)):
            errors.append(f"The username “{form['username']}” is already taken.")
        if len(password) < 8:
            errors.append("Choose a password of at least 8 characters.")
        elif password != confirm:
            errors.append("The two passwords don't match.")
        if errors:
            for e in errors:
                flash(e, "error")
        else:
            new_id = execute(
                "INSERT INTO tbl_adopter (adopter_name, adopter_contact, adopter_email, adopter_address, adopter_profile, "
                "adopter_username, adopter_password) VALUES (?, ?, ?, ?, '', ?, ?)",
                (form["name"], form["contact"], form["email"], form["address"], form["username"], hash_password(password)),
            )
            execute("INSERT INTO tbl_activity_log (user_id, log_type, details, date_time) VALUES (NULL, 'add', ?, datetime('now','localtime'))",
                    (f"New adopter signed up online: {form['name']}",))
            session["register_last"] = time.time()
            session["member_kind"], session["member_id"] = "adopter", new_id
            flash("Your account is ready. Find a pet you'd like to meet and send a request.", "success")
            return redirect(url_for("portal.home"))
    return render_template("portal/register.html", form=form)


@bp.route("/logout", methods=["POST"])
def logout():
    session.pop("member_kind", None)
    session.pop("member_id", None)
    flash("You've been signed out.", "success")
    return redirect(url_for("public.home"))


# ---------- account home ----------
@bp.route("/")
@member_required()
def home():
    m = g.member
    if m["kind"] == "adopter":
        requests_ = query("""SELECT r.*, p.pet_name, p.pet_profile_image, p.adoption_status
                             FROM tbl_adoption_request r LEFT JOIN tbl_pet p ON p.pet_id = r.pet_id
                             WHERE r.adopter_id = ? ORDER BY r.adoption_request_id DESC""", (m["id"],))
        adopted = query("""SELECT a.*, p.pet_name, p.pet_profile_image, pt.pet_type_name
                           FROM tbl_adoption a JOIN tbl_pet p ON p.pet_id = a.pet_id
                           LEFT JOIN tbl_pet_type pt ON pt.pet_type_id = p.pet_type_id
                           WHERE a.adopter_id = ? ORDER BY a.adoption_date DESC""", (m["id"],))
        return render_template("portal/home.html", requests=requests_, adopted=adopted)
    pets = query("""SELECT p.*, pt.pet_type_name, a.adoption_date
                    FROM tbl_pet p LEFT JOIN tbl_pet_type pt ON pt.pet_type_id = p.pet_type_id
                    LEFT JOIN tbl_adoption a ON a.pet_id = p.pet_id
                    WHERE p.pet_owner_id = ? ORDER BY p.pet_id DESC""", (m["id"],))
    return render_template("portal/home.html", pets=pets)


@bp.route("/profile", methods=["GET", "POST"])
@member_required()
def profile():
    m = g.member
    cfg = KINDS[m["kind"]]
    p, table = cfg["p"], cfg["table"]
    if request.method == "POST":
        if request.form.get("action") == "password":
            current, new, confirm = (request.form.get(k, "") for k in ("current_password", "new_password", "confirm_password"))
            if not verify_password(m["password"], current):
                flash("Your current password is incorrect.", "error")
            elif len(new) < 8:
                flash("Your new password must be at least 8 characters.", "error")
            elif new != confirm:
                flash("The new passwords don't match.", "error")
            else:
                execute(f"UPDATE {table} SET {p}_password = ? WHERE {p}_id = ?", (hash_password(new), m["id"]))
                flash("Your password was changed.", "success")
        else:
            name = form_text(request.form, "name", 100)
            email = form_text(request.form, "email", 100)
            if not name:
                flash("Enter your full name.", "error")
            elif email and not EMAIL_RE.match(email):
                flash("Enter a valid email address.", "error")
            else:
                execute(f"UPDATE {table} SET {p}_name = ?, {p}_email = ?, {p}_contact = ?, {p}_address = ? WHERE {p}_id = ?",
                        (name, email, form_text(request.form, "contact", 30), form_text(request.form, "address", 255), m["id"]))
                flash("Your details were saved.", "success")
        return redirect(url_for("portal.profile"))
    return render_template("portal/profile.html")


# ---------- adoption requests (adopters) ----------
@bp.route("/requests", methods=["POST"])
@member_required("adopter")
def request_pet():
    pet_id = request.form.get("pet_id", type=int)
    pet = query("SELECT * FROM tbl_pet WHERE pet_id = ?", (pet_id,), one=True)
    if pet is None or pet["adoption_status"] == "Adopted":
        flash("That pet is no longer available for adoption.", "error")
        return redirect(url_for("public.home") + "#pets")
    if scalar("SELECT 1 FROM tbl_adoption_request WHERE pet_id = ? AND adopter_id = ? AND status IN ('Pending','Approved')",
              (pet_id, g.member["id"])):
        flash(f"You already have an open request for {pet['pet_name']}.", "error")
        return redirect(url_for("portal.home"))
    if scalar("SELECT COUNT(*) FROM tbl_adoption_request WHERE adopter_id = ? AND status = 'Pending'", (g.member["id"],)) >= 5:
        flash("You can have up to 5 requests waiting at once. Cancel one or wait for the shelter to reply.", "error")
        return redirect(url_for("portal.home"))
    message = form_text(request.form, "message", 2000)
    execute("INSERT INTO tbl_adoption_request (pet_id, adopter_id, request_date, status, message) VALUES (?, ?, ?, 'Pending', ?)",
            (pet_id, g.member["id"], date.today().isoformat(), message))
    execute("INSERT INTO tbl_activity_log (user_id, log_type, details, date_time) VALUES (NULL, 'add', ?, datetime('now','localtime'))",
            (f"{g.member['name']} requested to adopt {pet['pet_name']}",))
    flash(f"Your request to adopt {pet['pet_name']} was sent. The shelter will contact you, and you can follow it here.", "success")
    return redirect(url_for("portal.home"))


@bp.route("/requests/<int:request_id>/cancel", methods=["POST"])
@member_required("adopter")
def cancel_request(request_id):
    row = query("SELECT r.*, p.pet_name FROM tbl_adoption_request r LEFT JOIN tbl_pet p ON p.pet_id = r.pet_id "
                "WHERE r.adoption_request_id = ? AND r.adopter_id = ?", (request_id, g.member["id"]), one=True)
    if row is None:
        abort(404)
    if row["status"] != "Pending":
        flash("Only requests that are still waiting can be cancelled. Contact the shelter about this one.", "error")
    else:
        execute("DELETE FROM tbl_adoption_request WHERE adoption_request_id = ?", (request_id,))
        flash(f"Your request for {row['pet_name'] or 'this pet'} was cancelled.", "success")
    return redirect(url_for("portal.home"))
