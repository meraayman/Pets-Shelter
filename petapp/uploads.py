"""Safe file uploads. Files are stored outside /static and served through a route."""
import os
import uuid
from pathlib import Path

from flask import current_app
from werkzeug.utils import secure_filename

# folder name -> (is it public?, kind of file allowed)
FOLDERS = {
    "pets": (True, "image"),
    "logo": (True, "image"),
    "owners": (False, "image"),
    "adopters": (False, "image"),
    "users": (False, "image"),
    "health": (False, "document"),
    "vaccination": (False, "document"),
    "adoptions": (False, "document"),
}

IMAGE_EXT = {"jpg", "jpeg", "png", "gif", "webp"}
DOC_EXT = {"pdf", "doc", "docx", "jpg", "jpeg", "png"}


class UploadError(ValueError):
    pass


def upload_dir(folder):
    return Path(current_app.root_path).parent / "uploads" / folder


def _looks_like_image(head):
    return (
        head.startswith(b"\xff\xd8\xff")                       # JPEG
        or head.startswith(b"\x89PNG\r\n\x1a\n")               # PNG
        or head[:6] in (b"GIF87a", b"GIF89a")                  # GIF
        or (head[:4] == b"RIFF" and head[8:12] == b"WEBP")     # WebP
    )


def save_upload(file_storage, folder, name_hint=""):
    """Validate and save an uploaded file. Returns the stored file name, or None if no file was chosen."""
    if file_storage is None or not file_storage.filename:
        return None
    _public, kind = FOLDERS[folder]
    ext = file_storage.filename.rsplit(".", 1)[-1].lower() if "." in file_storage.filename else ""

    if kind == "image":
        head = file_storage.stream.read(16)
        file_storage.stream.seek(0)
        if ext not in IMAGE_EXT or not _looks_like_image(head):
            raise UploadError("Photos must be JPG, PNG, GIF or WebP images.")
    elif ext not in DOC_EXT:
        raise UploadError("Documents must be PDF, DOC, DOCX, JPG or PNG files.")

    base = secure_filename(name_hint)[:40] or folder
    filename = f"{base}_{uuid.uuid4().hex[:8]}.{ext}"
    target = upload_dir(folder)
    target.mkdir(parents=True, exist_ok=True)
    file_storage.save(target / filename)
    return filename


def delete_upload(folder, filename):
    """Remove an old file (ignores missing files and anything outside the folder)."""
    if not filename:
        return
    base = upload_dir(folder).resolve()
    path = (base / filename).resolve()
    if path.parent == base and path.is_file():
        try:
            os.remove(path)
        except OSError:
            pass
