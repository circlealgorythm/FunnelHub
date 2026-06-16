from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from fastapi import UploadFile

from funnelhub.config import Settings
from funnelhub.db.models import Autopost

SUPPORTED_IMAGE_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}


async def save_autopost_image(upload: UploadFile, settings: Settings) -> dict[str, Any]:
    content_type = (upload.content_type or "").lower()
    suffix = SUPPORTED_IMAGE_TYPES.get(content_type)
    if suffix is None:
        raise ValueError("Image must be JPEG, PNG, or WebP.")

    data = await upload.read()
    if not data:
        raise ValueError("Image file is empty.")
    if len(data) > settings.autopost_max_image_bytes:
        raise ValueError("Image file is too large.")

    upload_dir = Path(settings.autopost_upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    file_name = f"{uuid.uuid4()}{suffix}"
    path = upload_dir / file_name
    path.write_bytes(data)

    return {
        "image": {
            "path": str(path),
            "file_name": file_name,
            "original_file_name": upload.filename,
            "content_type": content_type,
            "size": len(data),
        }
    }


def get_autopost_image_metadata(post: Autopost) -> dict[str, Any] | None:
    image = (post.metadata_ or {}).get("image")
    return image if isinstance(image, dict) else None


def get_autopost_image_path(post: Autopost) -> Path | None:
    image = get_autopost_image_metadata(post)
    if image is None:
        return None
    raw_path = image.get("path")
    if not isinstance(raw_path, str) or not raw_path.strip():
        return None
    return Path(raw_path)


def delete_autopost_image(post: Autopost, settings: Settings) -> None:
    image_path = get_autopost_image_path(post)
    if image_path is None:
        return

    upload_root = Path(settings.autopost_upload_dir).resolve()
    resolved_path = image_path.resolve()
    if upload_root not in (resolved_path, *resolved_path.parents):
        return
    if resolved_path.exists() and resolved_path.is_file():
        resolved_path.unlink()

