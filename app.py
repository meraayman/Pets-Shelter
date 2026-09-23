"""Start the Pet Adoption System.

    python app.py                          start the website at http://127.0.0.1:5000
    python app.py --lan                    also allow other computers on your network to open it
    python app.py reset-password admin     set a new password for a user
    python app.py import-mysql dump.sql    load data exported from the old PHP/MySQL version
"""
import getpass
import sys
import threading
import webbrowser
from pathlib import Path

from petapp import create_app


def reset_password(app, username):
    from petapp.security import hash_password
    import sqlite3

    db = Path(app.instance_path) / "petadoption.db"
    conn = sqlite3.connect(db)
    if not conn.execute("SELECT 1 FROM tbl_user WHERE username = ?", (username,)).fetchone():
        print(f'No user called "{username}". Existing users:',
              ", ".join(r[0] for r in conn.execute("SELECT username FROM tbl_user")))
        return 1
    pw = getpass.getpass("New password (at least 8 characters): ")
    if len(pw) < 8 or pw != getpass.getpass("Type it again: "):
        print("Passwords were too short or didn't match. Nothing changed.")
        return 1
    conn.execute("UPDATE tbl_user SET password = ? WHERE username = ?", (hash_password(pw), username))
    conn.commit()
    print(f"Password for {username} was changed.")
    return 0


def main(argv):
    app = create_app()

    if argv[:1] == ["reset-password"]:
        if len(argv) < 2:
            print("Usage: python app.py reset-password <username>")
            return 1
        return reset_password(app, argv[1])

    if argv[:1] == ["import-mysql"]:
        if len(argv) < 2 or not Path(argv[1]).is_file():
            print("Usage: python app.py import-mysql path/to/export.sql")
            return 1
        from tools.import_mysql import import_dump
        answer = input("This replaces all current data with the data in the file. Continue? [y/N] ")
        if answer.strip().lower() != "y":
            print("Cancelled.")
            return 0
        summary, skipped = import_dump(argv[1], Path(app.instance_path) / "petadoption.db")
        print("Imported:\n  " + "\n  ".join(summary))
        if skipped:
            print("Not used by this version:", ", ".join(skipped))
        print("Copy the old uploaded files into the uploads folder too (see README).")
        return 0

    host = "0.0.0.0" if "--lan" in argv else "127.0.0.1"
    url = "http://127.0.0.1:5000"
    print(f"\n  Pet Adoption System is running at {url}\n  Staff sign in: {url}/login\n  Press Ctrl+C to stop.\n")
    if "--no-browser" not in argv:
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    app.run(host=host, port=5000, debug=False)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
