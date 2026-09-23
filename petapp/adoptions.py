"""Staff side of adoptions: review requests from adopters and record completed adoptions."""
from datetime import date

from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from .db import execute, query, scalar
from .helpers import REQUEST_STATUSES, form_text, log_activity
from .security import login_required
from .uploads import UploadError, delete_upload, save_upload

bp = Blueprint("adoptions", __name__, url_prefix="/admin")


def staff_badges():
    """Counts shown next to menu items."""
    return {
        "requests": scalar("SELECT COUNT(*) FROM tbl_adoption_request WHERE status = 'Pending'") or 0,
        "inquiries": scalar("SELECT COUNT(*) FROM tbl_inquiry WHERE status = 'New'") or 0,
    }


def _release_hold_if_unused(pet_id):
    """Put an on-hold pet back to Available when no approved request is holding it."""
    if not scalar("SELECT 1 FROM tbl_adoption_request WHERE pet_id = ? AND status = 'Approved'", (pet_id,)):
        execute("UPDATE tbl_pet SET adoption_status = 'Available' WHERE pet_id = ? AND adoption_status = 'Pending'", (pet_id,))


# =====================================================================
# Requests
# =====================================================================
@bp.route("/adoption-requests")
@login_required
def requests_list():
    status = request.args.get("status", "Pending")
    if status not in REQUEST_STATUSES + ["all"]:
        status = "Pending"
    sql = """SELECT r.*, p.pet_name, p.pet_profile_image, p.adoption_status,
                    a.adopter_name, a.adopter_email, a.adopter_contact, a.adopter_address, u.complete_name AS staff_name
             FROM tbl_adoption_request r
             LEFT JOIN tbl_pet p ON p.pet_id = r.pet_id
             LEFT JOIN tbl_adopter a ON a.adopter_id = r.adopter_id
             LEFT JOIN tbl_user u ON u.user_id = r.user_id"""
    rows = query(sql + ("" if status == "all" else " WHERE r.status = ?") + " ORDER BY r.adoption_request_id DESC",
                 () if status == "all" else (status,))
    counts = {s: 0 for s in REQUEST_STATUSES}
    for r in query("SELECT status, COUNT(*) n FROM tbl_adoption_request GROUP BY status"):
        counts[r["status"]] = r["n"]
    return render_template("admin/adoption_requests.html", rows=rows, status=status, counts=counts)


@bp.route("/adoption-requests/<int:request_id>/<action>", methods=["POST"])
@login_required
def request_action(request_id, action):
    r = query("""SELECT r.*, p.pet_name, p.adoption_status, a.adopter_name FROM tbl_adoption_request r
                 LEFT JOIN tbl_pet p ON p.pet_id = r.pet_id LEFT JOIN tbl_adopter a ON a.adopter_id = r.adopter_id
                 WHERE r.adoption_request_id = ?""", (request_id,), one=True)
    if r is None or action not in ("approve", "reject", "reopen"):
        abort(404)
    note = form_text(request.form, "remarks", 1000)
    today = date.today().isoformat()
    who = f"{r['adopter_name']} for {r['pet_name']}"

    if action == "approve":
        if r["status"] != "Pending":
            flash("Only waiting requests can be approved.", "error")
        elif r["adoption_status"] == "Adopted":
            flash(f"{r['pet_name']} has already been adopted.", "error")
        else:
            execute("UPDATE tbl_adoption_request SET status = 'Approved', approval_date = ?, remarks = ?, user_id = ? WHERE adoption_request_id = ?",
                    (today, note, g.user["user_id"], request_id))
            execute("UPDATE tbl_pet SET adoption_status = 'Pending' WHERE pet_id = ? AND adoption_status = 'Available'", (r["pet_id"],))
            log_activity("update", f"Approved adoption request: {who}")
            flash(f"Request approved. {r['pet_name']} is now on hold. Record the adoption once {r['adopter_name']} takes them home.", "success")
    elif action == "reject":
        if r["status"] == "Rejected":
            flash("That request was already declined.", "error")
        else:
            execute("UPDATE tbl_adoption_request SET status = 'Rejected', approval_date = ?, remarks = ?, user_id = ? WHERE adoption_request_id = ?",
                    (today, note, g.user["user_id"], request_id))
            if r["status"] == "Approved":
                _release_hold_if_unused(r["pet_id"])
            log_activity("update", f"Declined adoption request: {who}")
            flash("Request declined.", "success")
    else:  # reopen
        if r["status"] == "Pending" or r["adoption_status"] == "Adopted":
            flash("That request can't be reopened.", "error")
        else:
            was_approved = r["status"] == "Approved"
            execute("UPDATE tbl_adoption_request SET status = 'Pending', approval_date = NULL, user_id = ? WHERE adoption_request_id = ?",
                    (g.user["user_id"], request_id))
            if was_approved:
                _release_hold_if_unused(r["pet_id"])
            log_activity("update", f"Reopened adoption request: {who}")
            flash("Request moved back to waiting.", "success")
    return redirect(request.referrer or url_for("adoptions.requests_list"))


# =====================================================================
# Adoptions
# =====================================================================
@bp.route("/adoptions")
@login_required
def adoptions_list():
    rows = query("""SELECT ad.*, p.pet_name, p.pet_profile_image, pt.pet_type_name,
                           a.adopter_name, a.adopter_contact, a.adopter_email, u.complete_name AS staff_name
                    FROM tbl_adoption ad
                    LEFT JOIN tbl_pet p ON p.pet_id = ad.pet_id
                    LEFT JOIN tbl_pet_type pt ON pt.pet_type_id = p.pet_type_id
                    LEFT JOIN tbl_adopter a ON a.adopter_id = ad.adopter_id
                    LEFT JOIN tbl_user u ON u.user_id = ad.user_id
                    ORDER BY ad.adoption_date DESC, ad.adoption_id DESC""")
    return render_template("admin/adoptions.html", rows=rows)


@bp.route("/adoptions/new", methods=["GET", "POST"])
@login_required
def adoption_new():
    pets = query("""SELECT p.pet_id, p.pet_name, p.adoption_status, pt.pet_type_name FROM tbl_pet p
                    LEFT JOIN tbl_pet_type pt ON pt.pet_type_id = p.pet_type_id
                    WHERE p.adoption_status != 'Adopted' ORDER BY p.pet_name""")
    adopters = query("SELECT adopter_id, adopter_name, adopter_email FROM tbl_adopter ORDER BY adopter_name")

    data = {"adoption_date": date.today().isoformat(), "remarks": "",
            "pet_id": request.args.get("pet", type=int), "adopter_id": request.args.get("adopter", type=int)}
    from_request = request.args.get("request", type=int)
    if from_request:
        r = query("SELECT * FROM tbl_adoption_request WHERE adoption_request_id = ?", (from_request,), one=True)
        if r:
            data.update(pet_id=r["pet_id"], adopter_id=r["adopter_id"])

    if request.method == "POST":
        f = request.form
        data = {
            "pet_id": f.get("pet_id", type=int),
            "adopter_id": f.get("adopter_id", type=int),
            "adoption_date": f.get("adoption_date", ""),
            "remarks": form_text(f, "remarks", 2000),
        }
        errors = []
        pet = query("SELECT * FROM tbl_pet WHERE pet_id = ?", (data["pet_id"],), one=True) if data["pet_id"] else None
        adopter = query("SELECT * FROM tbl_adopter WHERE adopter_id = ?", (data["adopter_id"],), one=True) if data["adopter_id"] else None
        if pet is None:
            errors.append("Choose the pet that was adopted.")
        elif pet["adoption_status"] == "Adopted":
            errors.append(f"{pet['pet_name']} is already marked as adopted.")
        if adopter is None:
            errors.append("Choose the adopter. If they're new, add them under Adopters first.")
        try:
            d = date.fromisoformat(data["adoption_date"])
            if d > date.today():
                errors.append("The adoption date can't be in the future.")
        except ValueError:
            errors.append("Enter the adoption date.")
        doc = None
        if not errors:
            try:
                doc = save_upload(request.files.get("document"), "adoptions", pet["pet_name"])
            except UploadError as e:
                errors.append(str(e))
        if errors:
            for e in errors:
                flash(e, "error")
        else:
            execute("""INSERT INTO tbl_adoption (pet_id, adopter_id, adoption_date, upload_adoption_document, remarks, user_id)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (pet["pet_id"], adopter["adopter_id"], data["adoption_date"], doc, data["remarks"], g.user["user_id"]))
            execute("UPDATE tbl_pet SET adoption_status = 'Adopted' WHERE pet_id = ?", (pet["pet_id"],))
            # This adopter's request is fulfilled; anyone else waiting for this pet is told it's gone
            today = date.today().isoformat()
            execute("""UPDATE tbl_adoption_request SET status = 'Approved', approval_date = COALESCE(approval_date, ?), user_id = ?
                       WHERE pet_id = ? AND adopter_id = ? AND status IN ('Pending', 'Approved')""",
                    (today, g.user["user_id"], pet["pet_id"], adopter["adopter_id"]))
            execute("""UPDATE tbl_adoption_request SET status = 'Rejected', approval_date = ?, user_id = ?,
                              remarks = 'This pet was adopted by another family.'
                       WHERE pet_id = ? AND adopter_id != ? AND status IN ('Pending', 'Approved')""",
                    (today, g.user["user_id"], pet["pet_id"], adopter["adopter_id"]))
            log_activity("add", f"Recorded adoption: {pet['pet_name']} adopted by {adopter['adopter_name']}")
            flash(f"{pet['pet_name']} is now marked as adopted by {adopter['adopter_name']}.", "success")
            return redirect(url_for("adoptions.adoptions_list"))

    return render_template("admin/adoption_form.html", data=data, pets=pets, adopters=adopters)


@bp.route("/adoptions/<int:adoption_id>/undo", methods=["POST"])
@login_required
def adoption_undo(adoption_id):
    ad = query("""SELECT ad.*, p.pet_name, a.adopter_name FROM tbl_adoption ad
                  LEFT JOIN tbl_pet p ON p.pet_id = ad.pet_id LEFT JOIN tbl_adopter a ON a.adopter_id = ad.adopter_id
                  WHERE ad.adoption_id = ?""", (adoption_id,), one=True)
    if ad is None:
        abort(404)
    execute("DELETE FROM tbl_adoption WHERE adoption_id = ?", (adoption_id,))
    delete_upload("adoptions", ad["upload_adoption_document"])
    if not scalar("SELECT 1 FROM tbl_adoption WHERE pet_id = ?", (ad["pet_id"],)):
        execute("UPDATE tbl_pet SET adoption_status = 'Available' WHERE pet_id = ? AND adoption_status = 'Adopted'", (ad["pet_id"],))
    log_activity("delete", f"Removed adoption record: {ad['pet_name']} / {ad['adopter_name']}")
    flash(f"The adoption record was removed and {ad['pet_name'] or 'the pet'} is available again.", "success")
    return redirect(url_for("adoptions.adoptions_list"))
