"""Dashboard, activity log, inquiries, reports and backups."""
import csv
import io
import re
import sqlite3
import zipfile
from datetime import datetime
from pathlib import Path

from flask import (Blueprint, Response, abort, current_app, flash, g, redirect, render_template, request,
                   send_from_directory, url_for)

from .db import execute, get_db, query, scalar
from .helpers import INQUIRY_STATUSES, PET_STATUSES, age_label, log_activity
from .security import admin_required, login_required

bp = Blueprint("admin", __name__, url_prefix="/admin")


@bp.route("/")
@login_required
def dashboard():
    counts = {s: 0 for s in PET_STATUSES}
    for r in query("SELECT adoption_status, COUNT(*) n FROM tbl_pet GROUP BY adoption_status"):
        counts[r["adoption_status"]] = r["n"]
    total = sum(counts.values())
    needs_care = scalar("SELECT COUNT(*) FROM tbl_pet WHERE health_status = 'Needs Treatment' OR vaccination_status = 'Not Vaccinated'")
    new_inquiries = scalar("SELECT COUNT(*) FROM tbl_inquiry WHERE status = 'New'")
    waiting_requests = scalar("SELECT COUNT(*) FROM tbl_adoption_request WHERE status = 'Pending'")
    recent_adoptions = query("""SELECT ad.adoption_date, p.pet_name, p.pet_profile_image, a.adopter_name FROM tbl_adoption ad
                                LEFT JOIN tbl_pet p ON p.pet_id = ad.pet_id LEFT JOIN tbl_adopter a ON a.adopter_id = ad.adopter_id
                                ORDER BY ad.adoption_date DESC, ad.adoption_id DESC LIMIT 4""")
    by_type = query("""SELECT pt.pet_type_name, COUNT(p.pet_id) n FROM tbl_pet_type pt
                       LEFT JOIN tbl_pet p ON p.pet_type_id = pt.pet_type_id
                       GROUP BY pt.pet_type_id ORDER BY n DESC, pt.pet_type_name""")
    recent_pets = query("""SELECT p.*, pt.pet_type_name FROM tbl_pet p
                           LEFT JOIN tbl_pet_type pt ON pt.pet_type_id = p.pet_type_id
                           ORDER BY p.pet_id DESC LIMIT 5""")
    activity = query("""SELECT al.*, u.complete_name FROM tbl_activity_log al
                        LEFT JOIN tbl_user u ON u.user_id = al.user_id
                        ORDER BY al.date_time DESC, al.log_record_id DESC LIMIT 6""")
    hour = datetime.now().hour
    greeting = "Good morning" if hour < 12 else "Good afternoon" if hour < 18 else "Good evening"
    return render_template(
        "admin/dashboard.html",
        counts=counts, total=total, needs_care=needs_care, new_inquiries=new_inquiries,
        waiting_requests=waiting_requests, recent_adoptions=recent_adoptions,
        by_type=[dict(r) for r in by_type], recent_pets=recent_pets, activity=activity,
        greeting=greeting, today=datetime.now().strftime("%A, %B %d").replace(" 0", " "),
    )


@bp.route("/activity")
@login_required
def activity():
    rows = query("""SELECT al.*, u.complete_name FROM tbl_activity_log al
                    LEFT JOIN tbl_user u ON u.user_id = al.user_id
                    ORDER BY al.date_time DESC, al.log_record_id DESC""")
    return render_template("admin/activity.html", rows=rows)


# ---------- inquiries from the public contact form ----------
@bp.route("/inquiries")
@login_required
def inquiries():
    status = request.args.get("status")
    if status not in INQUIRY_STATUSES:
        status = None
    sql = "SELECT i.*, p.pet_name FROM tbl_inquiry i LEFT JOIN tbl_pet p ON p.pet_id = i.pet_id"
    rows = query(sql + (" WHERE i.status = ?" if status else "") + " ORDER BY i.created_at DESC",
                 (status,) if status else ())
    counts = {s: 0 for s in INQUIRY_STATUSES}
    for r in query("SELECT status, COUNT(*) n FROM tbl_inquiry GROUP BY status"):
        counts[r["status"]] = r["n"]
    return render_template("admin/inquiries.html", rows=rows, status=status, counts=counts, statuses=INQUIRY_STATUSES)


@bp.route("/inquiries/<int:inquiry_id>/status", methods=["POST"])
@login_required
def inquiry_status(inquiry_id):
    status = request.form.get("status")
    if status not in INQUIRY_STATUSES or not scalar("SELECT 1 FROM tbl_inquiry WHERE inquiry_id = ?", (inquiry_id,)):
        abort(404)
    execute("UPDATE tbl_inquiry SET status = ? WHERE inquiry_id = ?", (status, inquiry_id))
    log_activity("update", f"Marked inquiry #{inquiry_id} as {status}")
    flash(f"Inquiry marked as {status.lower()}.", "success")
    return redirect(request.referrer or url_for("admin.inquiries"))


@bp.route("/inquiries/<int:inquiry_id>/delete", methods=["POST"])
@login_required
def inquiry_delete(inquiry_id):
    row = query("SELECT * FROM tbl_inquiry WHERE inquiry_id = ?", (inquiry_id,), one=True)
    if row is None:
        abort(404)
    execute("DELETE FROM tbl_inquiry WHERE inquiry_id = ?", (inquiry_id,))
    log_activity("delete", f"Deleted inquiry #{inquiry_id} from {row['name']}")
    flash("Inquiry deleted.", "success")
    return redirect(url_for("admin.inquiries"))


# ---------- reports ----------
PET_BASE = """FROM tbl_pet p
              LEFT JOIN tbl_pet_type pt ON pt.pet_type_id = p.pet_type_id
              LEFT JOIN tbl_pet_owner po ON po.pet_owner_id = p.pet_owner_id"""

REPORTS = {
    "adoption": {
        "title": "Adoption status",
        "description": "Every pet with its type, age and whether it is available, pending or adopted.",
        "sql": f"""SELECT p.pet_name, pt.pet_type_name, p.age, p.gender, p.adoption_status,
                          po.pet_owner_name, p.date_registered {PET_BASE}
                   ORDER BY CASE p.adoption_status WHEN 'Available' THEN 0 WHEN 'Pending' THEN 1 ELSE 2 END, p.pet_name""",
        "columns": [("pet_name", "Pet"), ("pet_type_name", "Type"), ("age", "Age"), ("gender", "Sex"),
                    ("adoption_status", "Status"), ("pet_owner_name", "Brought in by"), ("date_registered", "Registered")],
        "summary": "SELECT adoption_status AS label, COUNT(*) AS n FROM tbl_pet GROUP BY adoption_status",
    },
    "health": {
        "title": "Health and vaccination",
        "description": "Pets that need treatment or vaccines are listed first, with which records are on file.",
        "sql": f"""SELECT p.pet_name, pt.pet_type_name, p.age, p.health_status, p.vaccination_status,
                          CASE WHEN p.upload_health_history IS NOT NULL AND p.upload_health_history != '' THEN 'Yes' ELSE 'No' END AS has_health,
                          CASE WHEN p.proof_of_vaccination IS NOT NULL AND p.proof_of_vaccination != '' THEN 'Yes' ELSE 'No' END AS has_proof,
                          p.adoption_status {PET_BASE}
                   ORDER BY (p.health_status = 'Needs Treatment') DESC, (p.vaccination_status = 'Not Vaccinated') DESC, p.pet_name""",
        "columns": [("pet_name", "Pet"), ("pet_type_name", "Type"), ("age", "Age"), ("health_status", "Health"),
                    ("vaccination_status", "Vaccines"), ("has_health", "Health record"), ("has_proof", "Vaccine proof"),
                    ("adoption_status", "Status")],
        "summary": """SELECT 'Need treatment' AS label, COUNT(*) AS n FROM tbl_pet WHERE health_status = 'Needs Treatment'
                      UNION ALL SELECT 'Not vaccinated', COUNT(*) FROM tbl_pet WHERE vaccination_status = 'Not Vaccinated'
                      UNION ALL SELECT 'Healthy and vaccinated', COUNT(*) FROM tbl_pet WHERE health_status = 'Healthy' AND vaccination_status = 'Vaccinated'""",
    },
    "types": {
        "title": "Pets by type",
        "description": "How many of each kind of animal the shelter has, and how many have been adopted.",
        "sql": """SELECT pt.pet_type_name, COUNT(p.pet_id) AS total,
                         SUM(p.adoption_status = 'Available') AS available,
                         SUM(p.adoption_status = 'Pending') AS pending,
                         SUM(p.adoption_status = 'Adopted') AS adopted,
                         ROUND(AVG(p.age), 1) AS avg_age
                  FROM tbl_pet_type pt LEFT JOIN tbl_pet p ON p.pet_type_id = pt.pet_type_id
                  GROUP BY pt.pet_type_id ORDER BY total DESC, pt.pet_type_name""",
        "columns": [("pet_type_name", "Type"), ("total", "Total"), ("available", "Available"),
                    ("pending", "Pending"), ("adopted", "Adopted"), ("avg_age", "Average age (years)")],
        "summary": None,
    },
    "adoptions": {
        "title": "Completed adoptions",
        "description": "Every recorded adoption with the pet, the adopter and the staff member who recorded it.",
        "sql": """SELECT ad.adoption_date, p.pet_name, pt.pet_type_name, a.adopter_name, a.adopter_contact,
                         a.adopter_email, u.complete_name AS staff_name, COALESCE(ad.remarks, '') AS remarks
                  FROM tbl_adoption ad
                  LEFT JOIN tbl_pet p ON p.pet_id = ad.pet_id
                  LEFT JOIN tbl_pet_type pt ON pt.pet_type_id = p.pet_type_id
                  LEFT JOIN tbl_adopter a ON a.adopter_id = ad.adopter_id
                  LEFT JOIN tbl_user u ON u.user_id = ad.user_id
                  ORDER BY ad.adoption_date DESC""",
        "columns": [("adoption_date", "Date"), ("pet_name", "Pet"), ("pet_type_name", "Type"), ("adopter_name", "Adopter"),
                    ("adopter_contact", "Phone"), ("adopter_email", "Email"), ("staff_name", "Recorded by"), ("remarks", "Notes")],
        "summary": """SELECT 'This month' AS label, COUNT(*) AS n FROM tbl_adoption WHERE strftime('%Y-%m', adoption_date) = strftime('%Y-%m', 'now', 'localtime')
                      UNION ALL SELECT 'This year', COUNT(*) FROM tbl_adoption WHERE strftime('%Y', adoption_date) = strftime('%Y', 'now', 'localtime')
                      UNION ALL SELECT 'All time', COUNT(*) FROM tbl_adoption""",
    },
    "owners": {
        "title": "Pet owners",
        "description": "Each person who brought pets to the shelter, with the pets registered under them.",
        "sql": """SELECT po.pet_owner_name, po.pet_owner_contact, po.pet_owner_email,
                         COUNT(p.pet_id) AS pet_count,
                         SUM(p.adoption_status = 'Adopted') AS adopted,
                         COALESCE(GROUP_CONCAT(p.pet_name, ', '), '') AS pet_names
                  FROM tbl_pet_owner po LEFT JOIN tbl_pet p ON p.pet_owner_id = po.pet_owner_id
                  GROUP BY po.pet_owner_id ORDER BY po.pet_owner_name""",
        "columns": [("pet_owner_name", "Owner"), ("pet_owner_contact", "Contact"), ("pet_owner_email", "Email"),
                    ("pet_count", "Pets"), ("adopted", "Adopted"), ("pet_names", "Pet names")],
        "summary": None,
    },
}


def _report_rows(key):
    rep = REPORTS[key]
    rows = []
    for r in query(rep["sql"]):
        row = dict(r)
        if "age" in row:
            row["age"] = age_label(row["age"])
        for k, v in row.items():
            if v is None:
                row[k] = "" if k not in ("available", "pending", "adopted") else 0
        rows.append(row)
    return rows


@bp.route("/reports")
@login_required
def reports():
    return render_template("admin/reports.html", reports=REPORTS)


@bp.route("/reports/<key>")
@login_required
def report(key):
    if key not in REPORTS:
        abort(404)
    rep = REPORTS[key]
    summary = query(rep["summary"]) if rep["summary"] else []
    return render_template("admin/report.html", key=key, rep=rep, rows=_report_rows(key), summary=summary,
                           generated=datetime.now())


@bp.route("/reports/<key>.csv")
@login_required
def report_csv(key):
    if key not in REPORTS:
        abort(404)
    rep = REPORTS[key]
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow([label for _, label in rep["columns"]])
    for row in _report_rows(key):
        writer.writerow([row.get(col, "") for col, _ in rep["columns"]])
    filename = f"{key}_report_{datetime.now():%Y-%m-%d}.csv"
    # BOM so Excel opens accented names correctly
    return Response("\ufeff" + out.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


# ---------- backups (admins only) ----------
BACKUP_RE = re.compile(r"^backup_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}\.zip$")


def _backup_dir():
    path = Path(current_app.instance_path) / "backups"
    path.mkdir(exist_ok=True)
    return path


@bp.route("/backups", methods=["GET", "POST"])
@admin_required
def backups():
    folder = _backup_dir()
    if request.method == "POST":
        stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        snapshot = folder / f"snapshot_{stamp}.db"
        dest = sqlite3.connect(snapshot)
        get_db().backup(dest)  # consistent copy even while the app is running
        dest.close()
        zip_path = folder / f"backup_{stamp}.zip"
        uploads = Path(current_app.root_path).parent / "uploads"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(snapshot, "petadoption.db")
            for f in uploads.rglob("*"):
                if f.is_file():
                    z.write(f, Path("uploads") / f.relative_to(uploads))
        snapshot.unlink()
        log_activity("add", f"Created backup {zip_path.name}")
        flash(f"Backup {zip_path.name} was created.", "success")
        return redirect(url_for("admin.backups"))

    files = []
    for f in sorted(folder.glob("backup_*.zip"), reverse=True):
        st = f.stat()
        files.append({"name": f.name, "size": st.st_size, "created": datetime.fromtimestamp(st.st_mtime)})
    return render_template("admin/backups.html", files=files)


@bp.route("/backups/<name>")
@admin_required
def backup_download(name):
    if not BACKUP_RE.match(name):
        abort(404)
    return send_from_directory(_backup_dir(), name, as_attachment=True)


@bp.route("/backups/<name>/delete", methods=["POST"])
@admin_required
def backup_delete(name):
    path = _backup_dir() / name
    if not BACKUP_RE.match(name) or not path.is_file():
        abort(404)
    path.unlink()
    log_activity("delete", f"Deleted backup {name}")
    flash(f"Backup {name} was deleted.", "success")
    return redirect(url_for("admin.backups"))
