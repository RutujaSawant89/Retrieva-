"""Secure file storage and upload validation.

Files are stored outside any web root under ``STORAGE_DIR/<org_id>/<document_id><ext>``.
User-supplied filenames are never used in paths. Content is checked against the declared
extension (magic bytes / text decodability) before it is accepted.
"""

from __future__ import annotations

import hashlib
import os
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from app.core.config import get_settings
from app.core.errors import PayloadTooLargeError, ValidationFailedError

FILE_TYPES = {
    ".pdf": ("pdf", "application/pdf"),
    ".docx": ("docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    ".txt": ("txt", "text/plain"),
    ".md": ("md", "text/markdown"),
    ".markdown": ("md", "text/markdown"),
    ".csv": ("csv", "text/csv"),
    ".html": ("html", "text/html"),
    ".htm": ("html", "text/html"),
}

_CHUNK = 1024 * 1024


@dataclass
class StoredFile:
    path: Path
    size: int
    sha256: str
    file_type: str
    mime_type: str


def classify(filename: str) -> tuple[str, str, str]:
    """Return ``(extension, file_type, mime_type)`` or raise for unsupported files."""
    ext = Path(filename).suffix.lower()
    settings = get_settings()
    if ext not in FILE_TYPES or ext not in settings.allowed_extensions:
        allowed = ", ".join(sorted({e for e in settings.allowed_extensions if e in FILE_TYPES}))
        raise ValidationFailedError(f"Unsupported file type '{ext or 'none'}'. Allowed: {allowed}")
    file_type, mime = FILE_TYPES[ext]
    return ext, file_type, mime


def safe_display_name(filename: str) -> str:
    name = os.path.basename(filename.replace("\\", "/")).strip()
    name = "".join(ch for ch in name if ch.isprintable())
    return (name or "untitled")[:255]


def _validate_content(path: Path, file_type: str) -> None:
    with path.open("rb") as handle:
        head = handle.read(8192)
    if not head:
        raise ValidationFailedError("The file is empty")
    if file_type == "pdf":
        if b"%PDF-" not in head[:1024]:
            raise ValidationFailedError("The file does not look like a PDF")
    elif file_type == "docx":
        if not head.startswith(b"PK"):
            raise ValidationFailedError("The file does not look like a DOCX document")
        try:
            with zipfile.ZipFile(path) as archive:
                names = set(archive.namelist())
                if "word/document.xml" not in names:
                    raise ValidationFailedError("The file is not a valid DOCX document")
                # Zip-bomb guard: reject archives that expand absurdly.
                expanded = sum(info.file_size for info in archive.infolist())
                if expanded > 50 * max(1, path.stat().st_size) and expanded > 200 * 1024 * 1024:
                    raise ValidationFailedError("The DOCX archive expands to an unsafe size")
        except zipfile.BadZipFile as exc:
            raise ValidationFailedError("The file is not a valid DOCX document") from exc
    else:
        if b"\x00" in head and not head.startswith((b"\xff\xfe", b"\xfe\xff")):
            raise ValidationFailedError("Text files must not contain binary data")


def org_dir(org_id: uuid.UUID) -> Path:
    path = get_settings().storage_dir / str(org_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def store_upload(stream: BinaryIO, org_id: uuid.UUID, document_id: uuid.UUID, filename: str) -> StoredFile:
    """Stream an upload to disk, enforcing the size limit and computing its SHA-256."""
    ext, file_type, mime = classify(filename)
    limit = get_settings().max_upload_bytes
    target = org_dir(org_id) / f"{document_id}{ext}"
    tmp = target.with_suffix(target.suffix + ".part")
    digest = hashlib.sha256()
    size = 0
    try:
        with tmp.open("wb") as out:
            while chunk := stream.read(_CHUNK):
                size += len(chunk)
                if size > limit:
                    raise PayloadTooLargeError(
                        f"File exceeds the {get_settings().max_upload_mb} MB limit",
                        details={"limit_bytes": limit},
                    )
                digest.update(chunk)
                out.write(chunk)
        _validate_content(tmp, file_type)
        tmp.replace(target)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
    return StoredFile(path=target, size=size, sha256=digest.hexdigest(), file_type=file_type, mime_type=mime)


def resolve(storage_path: str) -> Path:
    """Resolve a stored relative path, refusing anything outside the storage root."""
    root = get_settings().storage_dir.resolve()
    path = (root / storage_path).resolve()
    if root not in path.parents:
        raise ValidationFailedError("Invalid storage path")
    return path


def relative(path: Path) -> str:
    return path.resolve().relative_to(get_settings().storage_dir.resolve()).as_posix()


def extracted_path(storage_path: str) -> Path:
    return resolve(storage_path).with_suffix(".extracted.json")


def delete_files(storage_path: str) -> None:
    for path in (resolve(storage_path), extracted_path(storage_path)):
        path.unlink(missing_ok=True)
