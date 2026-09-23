"""Shelter records: pets, pet types, pet owners and adopters."""
from datetime import date

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from .db import execute, query, scalar
from .helpers import (GENDERS, HEALTH_STATUSES, PET_STATUSES, VACCINE_STATUSES, form_int, form_text,
                      log_activity)
from .security import hash_password, login_required
from .uploads import UploadError, delete_upload, save_upload

bp = Blueprint("records", __name__, url_prefix="/admin")


# =====================================================================
# Pets
# =====================================================================
@bp.route("/pets")
@login_required
def pets():
    status = request.args.get("status")
    if status not in PET_STATUSES:
        status = None
    sql = """SELECT p.*, pt.pet_type_name, po.pet_owner_name
             FROM tbl_pet p
             LEFT JOIN tbl_pet_type pt ON pt.pet_type_id = p.pet_type_id
             LEFT JOIN tbl_pet_owner po ON po.pet_owner_id = p.pet_owner_id"""
    rows = query(sql + (" WHERE p.adoption_status = ?" if status else "") + " ORDER BY p.pet_id DESC",
                 (status,) if status else ())
    counts = {s: 0 for s in PET_STATUSES}
    for r in query("SELECT adoption_status, COUNT(*) n FROM tbl_pet GROUP BY adoption_status"):
        counts[r["adoption_status"]] = r["n"]
    return render_template("admin/pets.html", pets=rows, status=status, counts=counts)


def _pet_form_choices():
    return {
        "owners": query("SELECT pet_owner_id, pet_owner_name FROM tbl_pet_owner ORDER BY pet_owner_name"),
        "types": query("SELECT pet_type_id, pet_type_name FROM tbl_pet_type ORDER BY pet_type_name"),
        "genders": GENDERS,
        "health_statuses": HEALTH_STATUSES,
        "vaccine_statuses": VACCINE_STATUSES,
        "pet_statuses": PET_STATUSES,
    }


def _read_pet_form():
    f = request.form
    data = {
        "pet_name": form_text(f, "pet_name", 100),
        "pet_owner_id": form_int(f, "pet_owner_id"),
        "pet_type_id": form_int(f, "pet_type_id"),
        "description": form_text(f, "description", 3000),
        "age": form_int(f, "age"),
        "gender": f.get("gender"),
        "health_status": f.get("health_status"),
        "vaccination_status": f.get("vaccination_status"),
        "adoption_status": f.get("adoption_status"),
    }
    errors = []
    if not data["pet_name"]:
        errors.append("Enter the pet's name.")
    if data["pet_type_id"] is None:
        errors.append("Choose a pet type.")
    if data["age"] is None or not 0 <= data["age"] <= 60:
        errors.append("Enter an age between 0 and 60 years.")
    if data["gender"] not in GENDERS:
        errors.append("Choose male or female.")
    if data["health_status"] not in HEALTH_STATUSES:
        errors.append("Choose a health status.")
    if data["vaccination_status"] not in VACCINE_STATUSES:
        errors.append("Choose a vaccination status.")
    if data["adoption_status"] not in PET_STATUSES:
        errors.append("Choose an adoption status.")
    return data, errors


def _save_pet_files(pet, name):
    """Save any new photo/documents. Returns dict of changed columns."""
    changes = {}
    for field, folder in (("pet_profile_image", "pets"), ("upload_health_history", "health"),
                          ("proof_of_vaccination", "vaccination")):
        stored = save_upload(request.files.get(field), folder, name)
        if stored:
            if pet and pet[field]:
                delete_upload(folder, pet[field])
            changes[field] = stored
    for field, folder in (("upload_health_history", "health"), ("proof_of_vaccination", "vaccination")):
        if pet and request.form.get("remove_" + field) and field not in changes:
            delete_upload(folder, pet[field])
            changes[field] = None
    return changes


@bp.route("/pets/new", methods=["GET", "POST"])
@login_required
def pet_new():
    data = {"adoption_status": "Available", "health_status": "Healthy", "vaccination_status": "Not Vaccinated"}
    if request.method == "POST":
        data, errors = _read_pet_form()
        if not request.files.get("pet_profile_image") or not request.files["pet_profile_image"].filename:
            errors.append("Add a photo of the pet.")
        if not errors:
            try:
                files = _save_pet_files(None, data["pet_name"])
            except UploadError as e:
                errors.append(str(e))
        if errors:
            for e in errors:
                flash(e, "error")
        else:
            data.update(files)
            data["date_registered"] = date.today().isoformat()
            cols = ", ".join(data)
            execute(f"INSERT INTO tbl_pet ({cols}) VALUES ({', '.join('?' * len(data))})", tuple(data.values()))
            log_activity("add", f"Added new pet: {data['pet_name']}")
            flash(f"{data['pet_name']} was added.", "success")
            return redirect(url_for("records.pets"))
    return render_template("admin/pet_form.html", pet=data, is_new=True, **_pet_form_choices())


@bp.route("/pets/<int:pet_id>/edit", methods=["GET", "POST"])
@login_required
def pet_edit(pet_id):
    pet = query("SELECT * FROM tbl_pet WHERE pet_id = ?", (pet_id,), one=True)
    if pet is None:
        abort(404)
    data = dict(pet)
    if request.method == "POST":
        new, errors = _read_pet_form()
        data.update(new)
        if not errors:
            try:
                new.update(_save_pet_files(pet, new["pet_name"]))
            except UploadError as e:
                errors.append(str(e))
        if errors:
            for e in errors:
                flash(e, "error")
        else:
            changed = [k for k, v in new.items() if pet[k] != v]
            if changed:
                sets = ", ".join(f"{k} = ?" for k in new)
                execute(f"UPDATE tbl_pet SET {sets} WHERE pet_id = ?", (*new.values(), pet_id))
                log_activity("update", f"Updated pet {pet['pet_name']}: " + ", ".join(k.replace("_", " ") for k in changed))
                flash(f"Changes to {new['pet_name']} were saved.", "success")
            else:
                flash("No changes to save.", "success")
            return redirect(url_for("records.pets"))
    return render_template("admin/pet_form.html", pet=data, is_new=False, **_pet_form_choices())


@bp.route("/pets/<int:pet_id>/delete", methods=["POST"])
@login_required
def pet_delete(pet_id):
    pet = query("SELECT * FROM tbl_pet WHERE pet_id = ?", (pet_id,), one=True)
    if pet is None:
        abort(404)
    if scalar("SELECT 1 FROM tbl_adoption WHERE pet_id = ?", (pet_id,)):
        flash(f"{pet['pet_name']} has an adoption record. Remove it under Adoptions first if you really want to delete this pet.", "error")
        return redirect(url_for("records.pets"))
    execute("DELETE FROM tbl_adoption_request WHERE pet_id = ?", (pet_id,))
    execute("DELETE FROM tbl_pet WHERE pet_id = ?", (pet_id,))
    delete_upload("pets", pet["pet_profile_image"])
    delete_upload("health", pet["upload_health_history"])
    delete_upload("vaccination", pet["proof_of_vaccination"])
    log_activity("delete", f"Deleted pet: {pet['pet_name']}")
    flash(f"{pet['pet_name']} was deleted.", "success")
    return redirect(url_for("records.pets"))


# =====================================================================
# Pet types
# =====================================================================
@bp.route("/pet-types", methods=["GET", "POST"])
@login_required
def pet_types():
    if request.method == "POST":
        name = form_text(request.form, "pet_type_name", 100)
        if not name:
            flash("Enter a name for the pet type.", "error")
        elif scalar("SELECT 1 FROM tbl_pet_type WHERE lower(pet_type_name) = lower(?)", (name,)):
            flash(f"“{name}” already exists.", "error")
        else:
            execute("INSERT INTO tbl_pet_type (pet_type_name) VALUES (?)", (name,))
            log_activity("add", f"Added pet type: {name}")
            flash(f"“{name}” was added.", "success")
        return redirect(url_for("records.pet_types"))
    rows = query("""SELECT pt.*, COUNT(p.pet_id) AS pet_count FROM tbl_pet_type pt
                    LEFT JOIN tbl_pet p ON p.pet_type_id = pt.pet_type_id
                    GROUP BY pt.pet_type_id ORDER BY pt.pet_type_name""")
    return render_template("admin/pet_types.html", types=rows)


@bp.route("/pet-types/<int:type_id>/edit", methods=["POST"])
@login_required
def pet_type_edit(type_id):
    row = query("SELECT * FROM tbl_pet_type WHERE pet_type_id = ?", (type_id,), one=True)
    if row is None:
        abort(404)
    name = form_text(request.form, "pet_type_name", 100)
    if not name:
        flash("Enter a name for the pet type.", "error")
    elif scalar("SELECT 1 FROM tbl_pet_type WHERE lower(pet_type_name) = lower(?) AND pet_type_id != ?", (name, type_id)):
        flash(f"“{name}” already exists.", "error")
    elif name != row["pet_type_name"]:
        execute("UPDATE tbl_pet_type SET pet_type_name = ? WHERE pet_type_id = ?", (name, type_id))
        log_activity("update", f"Renamed pet type {row['pet_type_name']} to {name}")
        flash("Pet type renamed.", "success")
    return redirect(url_for("records.pet_types"))


@bp.route("/pet-types/<int:type_id>/delete", methods=["POST"])
@login_required
def pet_type_delete(type_id):
    row = query("SELECT * FROM tbl_pet_type WHERE pet_type_id = ?", (type_id,), one=True)
    if row is None:
        abort(404)
    used = scalar("SELECT COUNT(*) FROM tbl_pet WHERE pet_type_id = ?", (type_id,))
    if used:
        flash(f"“{row['pet_type_name']}” is used by {used} pet(s). Change their type first.", "error")
    else:
        execute("DELETE FROM tbl_pet_type WHERE pet_type_id = ?", (type_id,))
        log_activity("delete", f"Deleted pet type: {row['pet_type_name']}")
        flash(f"“{row['pet_type_name']}” was deleted.", "success")
    return redirect(url_for("records.pet_types"))


# =====================================================================
# Pet owners and adopters (same fields, so they share one set of pages)
# =====================================================================
PEOPLE = {
    "owners": {
        "table": "tbl_pet_owner", "p": "pet_owner", "folder": "owners",
        "one": "pet owner", "title": "Pet owners", "icon": "fa-user-tag",
        "intro": "People who brought pets to the shelter.",
    },
    "adopters": {
        "table": "tbl_adopter", "p": "adopter", "folder": "adopters",
        "one": "adopter", "title": "Adopters", "icon": "fa-hand-holding-heart",
        "intro": "People who have adopted or want to adopt a pet.",
    },
}


def _kind(kind):
    if kind not in PEOPLE:
        abort(404)
    return PEOPLE[kind]


def _person(cfg, pid):
    row = query(f"SELECT * FROM {cfg['table']} WHERE {cfg['p']}_id = ?", (pid,), one=True)
    if row is None:
        abort(404)
    # Normalise column names so templates don't care which table it came from
    p = cfg["p"]
    return {k.replace(p + "_", ""): v for k, v in dict(row).items()}


@bp.route("/<kind>")
@login_required
def people(kind):
    cfg = _kind(kind)
    p = cfg["p"]
    extra = ", (SELECT COUNT(*) FROM tbl_pet WHERE pet_owner_id = t.pet_owner_id) AS pet_count" if kind == "owners" else ""
    rows = query(f"SELECT t.*{extra} FROM {cfg['table']} t ORDER BY {p}_name")
    rows = [{k.replace(p + "_", ""): v for k, v in dict(r).items()} for r in rows]
    return render_template("admin/people.html", people=rows, kind=kind, cfg=cfg)


@bp.route("/<kind>/new", methods=["GET", "POST"])
@bp.route("/<kind>/<int:pid>/edit", methods=["GET", "POST"])
@login_required
def person_form(kind, pid=None):
    cfg = _kind(kind)
    p, table = cfg["p"], cfg["table"]
    person = _person(cfg, pid) if pid else {}
    data = dict(person)

    if request.method == "POST":
        f = request.form
        new = {
            "name": form_text(f, "name", 100),
            "contact": form_text(f, "contact", 30),
            "email": form_text(f, "email", 100),
            "address": form_text(f, "address", 255),
            "username": form_text(f, "username", 50),
        }
        password = f.get("password", "")
        data.update(new)
        errors = []
        if not new["name"]:
            errors.append("Enter a name.")
        if not new["username"]:
            errors.append("Enter a username.")
        elif scalar(f"SELECT 1 FROM {table} WHERE lower({p}_username) = lower(?) AND {p}_id != ?", (new["username"], pid or 0)):
            errors.append(f"The username “{new['username']}” is already taken.")
        if not pid and len(password) < 8:
            errors.append("Set a password of at least 8 characters.")
        elif password and len(password) < 8:
            errors.append("New passwords must be at least 8 characters.")
        if not errors:
            try:
                photo = save_upload(request.files.get("profile"), cfg["folder"], new["name"])
            except UploadError as e:
                errors.append(str(e))
        if errors:
            for e in errors:
                flash(e, "error")
        else:
            if photo:
                delete_upload(cfg["folder"], person.get("profile"))
                new["profile"] = photo
            if password:
                new["password"] = hash_password(password)
            cols = {f"{p}_{k}": v for k, v in new.items()}
            if pid:
                sets = ", ".join(f"{c} = ?" for c in cols)
                execute(f"UPDATE {table} SET {sets} WHERE {p}_id = ?", (*cols.values(), pid))
                log_activity("update", f"Updated {cfg['one']}: {new['name']}")
                flash(f"Changes to {new['name']} were saved.", "success")
            else:
                cols.setdefault(f"{p}_profile", "")
                execute(f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})", tuple(cols.values()))
                log_activity("add", f"Added {cfg['one']}: {new['name']}")
                flash(f"{new['name']} was added.", "success")
            return redirect(url_for("records.people", kind=kind))

    return render_template("admin/person_form.html", person=data, kind=kind, cfg=cfg, is_new=pid is None)


@bp.route("/<kind>/<int:pid>/delete", methods=["POST"])
@login_required
def person_delete(kind, pid):
    cfg = _kind(kind)
    person = _person(cfg, pid)
    if kind == "owners":
        count = scalar("SELECT COUNT(*) FROM tbl_pet WHERE pet_owner_id = ?", (pid,))
        if count:
            flash(f"{person['name']} is listed as the owner of {count} pet(s). Reassign or delete those pets first.", "error")
            return redirect(url_for("records.people", kind=kind))
    if kind == "adopters":
        count = scalar("SELECT COUNT(*) FROM tbl_adoption WHERE adopter_id = ?", (pid,))
        if count:
            flash(f"{person['name']} has {count} adoption record(s), so their details are kept for your records.", "error")
            return redirect(url_for("records.people", kind=kind))
        for r in query("SELECT pet_id FROM tbl_adoption_request WHERE adopter_id = ? AND status = 'Approved'", (pid,)):
            execute("UPDATE tbl_adoption_request SET status = 'Rejected' WHERE adopter_id = ? AND pet_id = ?", (pid, r["pet_id"]))
            if not scalar("SELECT 1 FROM tbl_adoption_request WHERE pet_id = ? AND status = 'Approved'", (r["pet_id"],)):
                execute("UPDATE tbl_pet SET adoption_status = 'Available' WHERE pet_id = ? AND adoption_status = 'Pending'", (r["pet_id"],))
        execute("DELETE FROM tbl_adoption_request WHERE adopter_id = ?", (pid,))
    execute(f"DELETE FROM {cfg['table']} WHERE {cfg['p']}_id = ?", (pid,))
    delete_upload(cfg["folder"], person.get("profile"))
    log_activity("delete", f"Deleted {cfg['one']}: {person['name']}")
    flash(f"{person['name']} was deleted.", "success")
    return redirect(url_for("records.people", kind=kind))
