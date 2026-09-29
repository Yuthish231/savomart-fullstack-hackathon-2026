"""Media storage. Local disk for the prototype; the interface is what an S3 backend would implement."""

import uuid
from pathlib import Path

from app.core.config import get_settings
from app.core.errors import AppError

MAX_BYTES = 8 * 1024 * 1024
ALLOWED = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}


def save_image(folder: str, content: bytes, content_type: str) -> tuple[str, int]:
    """Returns (public path under /media, size)."""
    ext = ALLOWED.get((content_type or "").lower())
    if ext is None:
        raise AppError("UNSUPPORTED_MEDIA", "Photos must be JPEG, PNG or WebP", 415)
    if len(content) > MAX_BYTES:
        raise AppError("FILE_TOO_LARGE", "Photos must be under 8 MB", 413)
    # Magic-byte check: don't trust the declared content type alone.
    if not (content[:3] == b"\xff\xd8\xff" or content[:8] == b"\x89PNG\r\n\x1a\n"
            or (content[:4] == b"RIFF" and content[8:12] == b"WEBP")):
        raise AppError("UNSUPPORTED_MEDIA", "That file doesn't look like an image", 415)
    rel = Path(folder) / f"{uuid.uuid4().hex}{ext}"
    dest = Path(get_settings().media_dir) / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(content)
    return "/media/" + rel.as_posix(), len(content)
