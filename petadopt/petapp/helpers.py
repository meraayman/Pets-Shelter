"""Shared helpers: activity log, company info and template filters."""
from datetime import datetime

from flask import g

from .db import execute, query

STATUS_CLASS = {
    "Available": "ok",
    "Healthy": "ok",
    "Vaccinated": "ok",
    "Replied": "ok",
    "Approved": "ok",
    "Rejected": "alert",
    "Waiting": "wait",
    "Declined": "alert",
    "Pending": "wait",
    "New": "wait",
    "Needs Treatment": "alert",
    "Not Vaccinated": "alert",
}

PET_STATUSES = ["Available", "Pending", "Adopted"]
HEALTH_STATUSES = ["Healthy", "Needs Treatment"]
VACCINE_STATUSES = ["Vaccinated", "Not Vaccinated"]
GENDERS = ["Male", "Female"]
INQUIRY_STATUSES = ["New", "Replied", "Closed"]
REQUEST_STATUSES = ["Pending", "Approved", "Rejected"]


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log_activity(log_type, details):
    """Record who changed what (shown on the Activity log page)."""
    user_id = g.user["user_id"] if getattr(g, "user", None) else None
    execute(
        "INSERT INTO tbl_activity_log (user_id, log_type, details, date_time) VALUES (?, ?, ?, ?)",
        (user_id, log_type, details, now()),
    )


def get_company():
    if "company" not in g:
        row = query("SELECT * FROM tbl_company ORDER BY company_id LIMIT 1", one=True)
        company = dict(row) if row else {}
        company.setdefault("company_id", None)
        for key in ("company_logo", "company_name", "company_address", "company_contact", "company_website"):
            company[key] = company.get(key) or ""
        company["company_name"] = company["company_name"] or "Pet Adoption Center"
        g.company = company
    return g.company


def form_text(form, name, max_len=255):
    return (form.get(name) or "").strip()[:max_len]


def form_int(form, name, default=None):
    try:
        return int(form.get(name, ""))
    except (TypeError, ValueError):
        return default


# ---------- template filters ----------
def _parse(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(str(value)[:19], fmt)
        except ValueError:
            continue
    return None


def fmt_date(value):
    d = _parse(value)
    return d.strftime("%b %d, %Y").replace(" 0", " ") if d else (value or "")


def fmt_datetime(value):
    d = _parse(value)
    return d.strftime("%b %d, %Y %I:%M %p").replace(" 0", " ") if d else (value or "")


def age_label(age):
    try:
        age = int(age)
    except (TypeError, ValueError):
        return "Age unknown"
    if age <= 0:
        return "Under 1 year"
    return f"{age} year" if age == 1 else f"{age} years"


def status_class(status):
    return STATUS_CLASS.get(status, "done")


def register_template_helpers(app):
    app.add_template_filter(fmt_date, "date")
    app.add_template_filter(fmt_datetime, "datetime")
    app.add_template_filter(age_label, "age")
    app.add_template_filter(status_class, "status_class")
