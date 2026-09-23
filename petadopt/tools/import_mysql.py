"""Import data from the old PHP/MySQL version (a phpMyAdmin .sql export).

Usage:  python app.py import-mysql path/to/inet_pet_adoption_db.sql

It replaces the current data in instance/petadoption.db with the rows in the dump.
Old password hashes keep working; they're upgraded the next time each person signs in.
"""
import html
import re
import sqlite3

TABLES = ["tbl_company", "tbl_user", "tbl_pet_type", "tbl_pet_owner", "tbl_adopter", "tbl_pet",
          "tbl_pet_media", "tbl_adoption", "tbl_adoption_request", "tbl_activity_log", "tbl_inquiry"]

INSERT_RE = re.compile(r"INSERT INTO `(\w+)` \(([^)]*)\) VALUES\s*", re.I)


def _parse_values(text, pos):
    """Parse (...),(...); starting at pos. Returns (rows, end_pos)."""
    rows, row, i, n = [], None, pos, len(text)
    while i < n:
        c = text[i]
        if c == "(" and row is None:
            row, i = [], i + 1
            continue
        if row is None:
            if c == ";":
                return rows, i + 1
            i += 1
            continue
        if c in " \t\r\n,":
            i += 1
            continue
        if c == ")":
            rows.append(row)
            row, i = None, i + 1
            continue
        if c == "'":  # quoted string with MySQL escapes
            i += 1
            buf = []
            while i < n:
                ch = text[i]
                if ch == "\\" and i + 1 < n:
                    nxt = text[i + 1]
                    buf.append({"n": "\n", "r": "\r", "t": "\t", "0": "\0", "Z": "\x1a"}.get(nxt, nxt))
                    i += 2
                elif ch == "'" and i + 1 < n and text[i + 1] == "'":
                    buf.append("'")
                    i += 2
                elif ch == "'":
                    i += 1
                    break
                else:
                    buf.append(ch)
                    i += 1
            row.append("".join(buf))
            continue
        m = re.compile(r"NULL|-?\d+(?:\.\d+)?", re.I).match(text, i)
        if not m:
            raise ValueError(f"Can't read value near: {text[i:i + 40]!r}")
        tok = m.group(0)
        row.append(None if tok.upper() == "NULL" else (float(tok) if "." in tok else int(tok)))
        i = m.end()
    return rows, i


def import_dump(sql_path, db_path):
    text = open(sql_path, encoding="utf-8", errors="replace").read()
    data = {}
    for m in INSERT_RE.finditer(text):
        table = m.group(1)
        cols = [c.strip().strip("`") for c in m.group(2).split(",")]
        rows, _ = _parse_values(text, m.end())
        data.setdefault(table, (cols, []))[1].extend(rows)

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = OFF")
    existing = {r[0]: [c[1] for c in conn.execute(f"PRAGMA table_info({r[0]})")]
                for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    summary = []
    for table in TABLES:
        if table not in data or table not in existing:
            continue
        cols, rows = data[table]
        keep = [i for i, c in enumerate(cols) if c in existing[table]]
        use_cols = [cols[i] for i in keep]
        conn.execute(f"DELETE FROM {table}")
        for r in rows:
            vals = []
            for i in keep:
                v = r[i]
                # the PHP version saved text with htmlspecialchars(); undo that
                if isinstance(v, str) and not v.startswith("$2"):
                    v = html.unescape(v)
                vals.append(v)
            conn.execute(f"INSERT INTO {table} ({', '.join(use_cols)}) VALUES ({', '.join('?' * len(vals))})", vals)
        summary.append(f"{table}: {len(rows)} row(s)")
    skipped = sorted(set(data) - set(TABLES))
    conn.commit()
    conn.close()
    return summary, skipped
