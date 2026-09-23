"""Staff accounts, the signed-in user's profile, and shelter information."""
from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from .db import execute, query, scalar
from .helpers import form_text, get_company, log_activity
from .security import admin_required, hash_password, login_required, verify_password
from .uploads import UploadError, delete_upload, save_upload

bp = Blueprint("accounts", __name__, url_prefix="/admin")

USER_TYPES = ["user", "admin"]


# ---------- staff accounts (admins only) ----------
@bp.route("/users")
@admin_required
def users():
    rows = query("SELECT * FROM tbl_user ORDER BY complete_name")
    return render_template("admin/users.html", users=rows)


@bp.route("/users/new", methods=["GET", "POST"])
@bp.route("/users/<int:user_id>/edit", methods=["GET", "POST"])
@admin_required
def user_form(user_id=None):
    user = query("SELECT * FROM tbl_user WHERE user_id = ?", (user_id,), one=True) if user_id else None
    if user_id and user is None:
        abort(404)
    data = dict(user) if user else {"user_type": "user"}

    if request.method == "POST":
        f = request.form
        new = {
            "complete_name": form_text(f, "complete_name", 100),
            "designation": form_text(f, "designation", 255),
            "username": form_text(f, "username", 50),
            "user_type": f.get("user_type"),
        }
        password = f.get("password", "")
        data.update(new)
        errors = []
        if not new["complete_name"]:
            errors.append("Enter the person's full name.")
        if not new["username"]:
            errors.append("Enter a username.")
        elif scalar("SELECT 1 FROM tbl_user WHERE lower(username) = lower(?) AND user_id != ?", (new["username"], user_id or 0)):
            errors.append(f"The username “{new['username']}” is already taken.")
        if new["user_type"] not in USER_TYPES:
            errors.append("Choose an account type.")
        if user and user["user_id"] == g.user["user_id"] and new["user_type"] != "admin":
            errors.append("You can't remove admin access from your own account.")
        if not user_id and len(password) < 8:
            errors.append("Set a password of at least 8 characters.")
        elif password and len(password) < 8:
            errors.append("New passwords must be at least 8 characters.")
        photo = None
        if not errors:
            try:
                photo = save_upload(request.files.get("profile_image"), "users", new["complete_name"])
            except UploadError as e:
                errors.append(str(e))
        if errors:
            for e in errors:
                flash(e, "error")
        else:
            if photo:
                delete_upload("users", user["profile_image"] if user else None)
                new["profile_image"] = photo
            if password:
                new["password"] = hash_password(password)
            if user_id:
                sets = ", ".join(f"{k} = ?" for k in new)
                execute(f"UPDATE tbl_user SET {sets} WHERE user_id = ?", (*new.values(), user_id))
                log_activity("update", f"Updated user account: {new['username']}")
                flash(f"Changes to {new['complete_name']} were saved.", "success")
            else:
                new.setdefault("profile_image", "")
                execute(f"INSERT INTO tbl_user ({', '.join(new)}) VALUES ({', '.join('?' * len(new))})", tuple(new.values()))
                log_activity("add", f"Added user account: {new['username']}")
                flash(f"Account for {new['complete_name']} was created.", "success")
            return redirect(url_for("accounts.users"))

    return render_template("admin/user_form.html", user=data, is_new=user_id is None, user_types=USER_TYPES)


@bp.route("/users/<int:user_id>/delete", methods=["POST"])
@admin_required
def user_delete(user_id):
    user = query("SELECT * FROM tbl_user WHERE user_id = ?", (user_id,), one=True)
    if user is None:
        abort(404)
    if user_id == g.user["user_id"]:
        flash("You can't delete the account you're signed in with.", "error")
    else:
        execute("DELETE FROM tbl_user WHERE user_id = ?", (user_id,))
        delete_upload("users", user["profile_image"])
        log_activity("delete", f"Deleted user account: {user['username']}")
        flash(f"{user['complete_name']}'s account was deleted.", "success")
    return redirect(url_for("accounts.users"))


# ---------- my profile ----------
@bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    me = g.user
    if request.method == "POST":
        action = request.form.get("action")
        if action == "details":
            name = form_text(request.form, "complete_name", 100)
            designation = form_text(request.form, "designation", 255)
            if not name:
                flash("Enter your full name.", "error")
            else:
                try:
                    photo = save_upload(request.files.get("profile_image"), "users", name)
                except UploadError as e:
                    flash(str(e), "error")
                    return redirect(url_for("accounts.profile"))
                if photo:
                    delete_upload("users", me["profile_image"])
                execute("UPDATE tbl_user SET complete_name = ?, designation = ?, profile_image = ? WHERE user_id = ?",
                        (name, designation, photo or me["profile_image"], me["user_id"]))
                log_activity("update", "Updated own profile")
                flash("Your profile was saved.", "success")
        elif action == "password":
            current = request.form.get("current_password", "")
            new = request.form.get("new_password", "")
            confirm = request.form.get("confirm_password", "")
            if not verify_password(me["password"], current):
                flash("Your current password is incorrect.", "error")
            elif len(new) < 8:
                flash("Your new password must be at least 8 characters.", "error")
            elif new != confirm:
                flash("The new passwords don't match.", "error")
            else:
                execute("UPDATE tbl_user SET password = ? WHERE user_id = ?", (hash_password(new), me["user_id"]))
                log_activity("update", "Changed own password")
                flash("Your password was changed.", "success")
        return redirect(url_for("accounts.profile"))
    return render_template("admin/profile.html")


# ---------- shelter information (admins only) ----------
@bp.route("/shelter", methods=["GET", "POST"])
@admin_required
def company():
    c = get_company()
    if request.method == "POST":
        f = request.form
        new = {
            "company_name": form_text(f, "company_name", 150) or "Pet Adoption Center",
            "company_address": form_text(f, "company_address", 255),
            "company_contact": form_text(f, "company_contact", 100),
            "company_website": form_text(f, "company_website", 255),
        }
        if new["company_website"] and not new["company_website"].startswith(("http://", "https://")):
            new["company_website"] = "https://" + new["company_website"]
        try:
            logo = save_upload(request.files.get("company_logo"), "logo", "logo")
        except UploadError as e:
            flash(str(e), "error")
            return redirect(url_for("accounts.company"))
        if logo:
            delete_upload("logo", c["company_logo"])
            new["company_logo"] = logo
        sets = ", ".join(f"{k} = ?" for k in new)
        execute(f"UPDATE tbl_company SET {sets} WHERE company_id = ?", (*new.values(), c["company_id"]))
        log_activity("update", "Updated shelter information")
        flash("Shelter information was saved.", "success")
        return redirect(url_for("accounts.company"))
    return render_template("admin/company.html")
