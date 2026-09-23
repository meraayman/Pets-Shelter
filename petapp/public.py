"""Public website: pet listings and the contact form."""
import re
import time

from flask import Blueprint, flash, g, redirect, render_template, request, session, url_for

from .db import execute, query, scalar
from .helpers import form_text, now

bp = Blueprint("public", __name__)

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@bp.route("/")
def home():
    pets = query(
        """SELECT p.*, COALESCE(pt.pet_type_name, 'Other') AS pet_type_name
           FROM tbl_pet p LEFT JOIN tbl_pet_type pt ON pt.pet_type_id = p.pet_type_id
           WHERE p.adoption_status IN ('Available', 'Pending')
           ORDER BY CASE p.adoption_status WHEN 'Available' THEN 0 ELSE 1 END,
                    p.date_registered DESC, p.pet_id DESC"""
    )
    types = {}
    for p in pets:
        types[p["pet_type_name"]] = types.get(p["pet_type_name"], 0) + 1
    available = [p for p in pets if p["adoption_status"] == "Available"]
    adopted = scalar("SELECT COUNT(*) FROM tbl_pet WHERE adoption_status = 'Adopted'")
    requested = set()
    if g.member and g.member["kind"] == "adopter":
        requested = {r["pet_id"] for r in query(
            "SELECT pet_id FROM tbl_adoption_request WHERE adopter_id = ? AND status IN ('Pending','Approved')",
            (g.member["id"],))}
    return render_template(
        "public/home.html",
        pets=pets,
        types=sorted(types.items()),
        available_count=len(available),
        adopted_count=adopted,
        hero_pets=available[:3],
        requested=requested,
    )


@bp.route("/contact", methods=["GET", "POST"])
def contact():
    pet = None
    pet_id = request.values.get("pet", type=int)
    if pet_id:
        pet = query(
            "SELECT * FROM tbl_pet WHERE pet_id = ? AND adoption_status IN ('Available','Pending')",
            (pet_id,),
            one=True,
        )

    form = {"name": "", "email": "", "phone": "", "subject": f"Adopting {pet['pet_name']}" if pet else "", "message": ""}

    if request.method == "POST":
        form = {
            "name": form_text(request.form, "name", 100),
            "email": form_text(request.form, "email", 150),
            "phone": form_text(request.form, "phone", 30),
            "subject": form_text(request.form, "subject", 200),
            "message": form_text(request.form, "message", 3000),
        }
        error = None
        if request.form.get("website"):  # hidden spam trap; bots fill it in
            flash("Thanks, your message has been sent.", "success")
            return redirect(url_for("public.contact"))
        if time.time() - session.get("contact_last", 0) < 30:
            error = "Please wait a few seconds before sending another message."
        elif not (form["name"] and form["subject"] and form["message"]):
            error = "Fill in your name, subject and message."
        elif not EMAIL_RE.match(form["email"]):
            error = "Enter a valid email address so we can reply."

        if error:
            flash(error, "error")
        else:
            execute(
                "INSERT INTO tbl_inquiry (pet_id, name, email, phone, subject, message, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (pet["pet_id"] if pet else None, form["name"], form["email"], form["phone"] or None,
                 form["subject"], form["message"], now()),
            )
            session["contact_last"] = time.time()
            flash(f"Thanks, {form['name']}. Your message has been sent and we'll reply to {form['email']}.", "success")
            return redirect(url_for("public.contact", pet=pet["pet_id"] if pet else None))

    return render_template("public/contact.html", pet=pet, form=form)
