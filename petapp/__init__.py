"""Pet Adoption System (Flask + SQLite)."""
import secrets
from datetime import datetime
from pathlib import Path

from flask import Flask, abort, flash, g, redirect, render_template, request, send_from_directory, session, url_for
from werkzeug.exceptions import HTTPException

from . import db
from .helpers import get_company, register_template_helpers
from .security import check_csrf, csrf_field, csrf_token
from .uploads import FOLDERS, upload_dir
from .portal import load_member
from .adoptions import staff_badges

ROOT = Path(__file__).resolve().parent.parent


def _secret_key(instance_path):
    """Create a random secret key once and keep it in instance/secret_key."""
    key_file = Path(instance_path) / "secret_key"
    if not key_file.exists():
        key_file.write_text(secrets.token_hex(32), encoding="utf-8")
    return key_file.read_text(encoding="utf-8").strip()


def create_app():
    app = Flask(
        __name__,
        instance_path=str(ROOT / "instance"),
        template_folder=str(ROOT / "templates"),
        static_folder=str(ROOT / "static"),
    )
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    app.config.update(
        SECRET_KEY=_secret_key(app.instance_path),
        MAX_CONTENT_LENGTH=8 * 1024 * 1024,  # 8 MB per request
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
    )

    db.init_db(app)
    app.teardown_appcontext(db.close_db)
    register_template_helpers(app)

    @app.before_request
    def load_user_and_check_forms():
        g.user = None
        if session.get("user_id"):
            g.user = db.query("SELECT * FROM tbl_user WHERE user_id = ?", (session["user_id"],), one=True)
            if g.user is None:
                session.pop("user_id", None)
        g.member = load_member()
        check_csrf()

    @app.context_processor
    def template_globals():
        return {
            "company": get_company(),
            "current_user": g.get("user"),
            "csrf_field": csrf_field,
            "csrf_token": csrf_token,
            "now_year": datetime.now().year,
            "current_member": g.get("member"),
            "staff_badges": staff_badges() if g.get("user") else {},
        }

    # Uploaded files: pet photos and the logo are public, everything else needs sign-in
    @app.route("/uploads/<folder>/<path:filename>")
    def uploaded_file(folder, filename):
        if folder not in FOLDERS:
            abort(404)
        is_public, kind = FOLDERS[folder]
        if not is_public and g.user is None:
            abort(403)
        return send_from_directory(upload_dir(folder), filename, as_attachment=(kind == "document" and not filename.lower().endswith((".pdf", ".jpg", ".jpeg", ".png"))))

    from .public import bp as public_bp
    from .auth import bp as auth_bp
    from .admin import bp as admin_bp
    from .records import bp as records_bp
    from .accounts import bp as accounts_bp
    from .portal import bp as portal_bp
    from .adoptions import bp as adoptions_bp

    app.register_blueprint(public_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(records_bp)
    app.register_blueprint(accounts_bp)
    app.register_blueprint(portal_bp)
    app.register_blueprint(adoptions_bp)

    @app.errorhandler(413)
    def too_large(_e):
        flash("That file is too large. Please upload files under 8 MB.", "error")
        return redirect(request.referrer or url_for("public.home"))

    @app.errorhandler(HTTPException)
    def http_error(e):
        messages = {
            403: "You don't have permission to open this page.",
            404: "This page doesn't exist. It may have been moved or deleted.",
        }
        return render_template(
            "error.html",
            code=e.code,
            title=e.name,
            message=messages.get(e.code, e.description),
        ), e.code

    return app
