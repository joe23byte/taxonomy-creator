"""App-wide branding: a logo shown in the web header and in PDF reports (shared by all projects)."""
from __future__ import annotations

import io
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from . import projects

MAX_BYTES = 5 * 1024 * 1024
MAX_EDGE = 1200


class BrandingError(ValueError):
    pass


def logo_path() -> Path:
    return projects.data_dir() / "branding" / "logo.png"


def info() -> dict:
    path = logo_path()
    return {"logo": path.exists(), "version": int(path.stat().st_mtime) if path.exists() else None}


def save_logo(content: bytes) -> dict:
    """Validate and normalise an uploaded PNG/JPEG/WebP/GIF image to a PNG, at most MAX_EDGE px wide or high."""
    if len(content) > MAX_BYTES:
        raise BrandingError("Logo file is too large (max 5 MB)")
    try:
        img = Image.open(io.BytesIO(content))
        img.load()
    except (UnidentifiedImageError, OSError):
        raise BrandingError("Logo must be a PNG, JPEG, WebP or GIF image (SVG is not supported)")
    img = img.convert("RGBA")
    img.thumbnail((MAX_EDGE, MAX_EDGE))
    bbox = img.getbbox()
    if bbox:
        img = img.crop(bbox)
    path = logo_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    img.save(tmp, "PNG")
    tmp.replace(path)
    return info()


def delete_logo() -> dict:
    logo_path().unlink(missing_ok=True)
    return info()
