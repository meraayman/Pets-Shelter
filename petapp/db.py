"""SQLite database access. The whole database lives in instance/petadoption.db."""
import sqlite3
from pathlib import Path

from flask import current_app, g


def db_path():
    return Path(current_app.instance_path) / "petadoption.db"


def get_db():
    if "db" not in g:
        conn = sqlite3.connect(db_path(), detect_types=0, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        g.db = conn
    return g.db


def close_db(_exc=None):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def query(sql, params=(), one=False):
    cur = get_db().execute(sql, params)
    rows = cur.fetchall()
    cur.close()
    return (rows[0] if rows else None) if one else rows


def scalar(sql, params=()):
    row = get_db().execute(sql, params).fetchone()
    return row[0] if row else None


def execute(sql, params=()):
    conn = get_db()
    cur = conn.execute(sql, params)
    conn.commit()
    return cur.lastrowid


def init_db(app):
    """Create the database file and default records if it doesn't exist yet."""
    from .security import hash_password

    path = Path(app.instance_path) / "petadoption.db"
    fresh = not path.exists()
    conn = sqlite3.connect(path)
    schema = (Path(app.root_path).parent / "schema.sql").read_text(encoding="utf-8")
    conn.executescript(schema)
    _upgrade(conn)
    if fresh or conn.execute("SELECT COUNT(*) FROM tbl_user").fetchone()[0] == 0:
        conn.execute(
            "INSERT INTO tbl_user (username, password, complete_name, designation, profile_image, user_type) "
            "VALUES (?, ?, ?, ?, '', 'admin')",
            ("admin", hash_password("admin123"), "Administrator", "Has access to every feature"),
        )
    if conn.execute("SELECT COUNT(*) FROM tbl_company").fetchone()[0] == 0:
        conn.execute(
            "INSERT INTO tbl_company (company_logo, company_name, company_address, company_contact, company_website) "
            "VALUES ('', 'Pet Adoption Center', '', '', '')"
        )
    conn.commit()
    conn.close()
    return fresh


def _upgrade(conn):
    """Add columns introduced after the first Python release to existing databases."""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(tbl_adoption_request)")}
    if "message" not in cols:
        conn.execute("ALTER TABLE tbl_adoption_request ADD COLUMN message TEXT")
