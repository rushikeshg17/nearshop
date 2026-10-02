"""Image uploads behind a small storage interface (local disk now, S3 later).

Uploads are decoded with Pillow, so anything that is not a real image is rejected, then
re-encoded to WebP (this also strips EXIF/GPS metadata) and resized to a sane maximum.
"""
import io
import uuid

from fastapi import UploadFile
from PIL import Image, ImageOps, UnidentifiedImageError

from app.core.config import settings
from app.core.errors import AppError

MAX_SIDE = 1400
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP", "GIF"}


async def save_image(upload: UploadFile, folder: str) -> str:
    data = await upload.read(settings.max_upload_mb * 1024 * 1024 + 1)
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise AppError(f"Images must be under {settings.max_upload_mb} MB", code="file_too_large")
    try:
        img = Image.open(io.BytesIO(data))
        if img.format not in ALLOWED_FORMATS:
            raise AppError("Upload a JPG, PNG or WebP image", code="bad_image")
        img = ImageOps.exif_transpose(img).convert("RGB")
    except (UnidentifiedImageError, OSError):
        raise AppError("That file is not a readable image", code="bad_image") from None
    img.thumbnail((MAX_SIDE, MAX_SIDE))
    rel = f"{folder}/{uuid.uuid4().hex}.webp"
    dest = settings.media_dir / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    img.save(dest, "WEBP", quality=82, method=5)
    return rel


def delete_image(rel_path: str | None) -> None:
    if not rel_path:
        return
    path = (settings.media_dir / rel_path).resolve()
    if settings.media_dir.resolve() in path.parents and path.exists():
        path.unlink()
