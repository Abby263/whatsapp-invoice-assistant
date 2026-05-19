"""Lightweight image preprocessing before vision-model calls."""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass
from typing import Optional

from PIL import Image, ImageEnhance, ImageOps


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PreprocessedImage:
    content: bytes
    mime_type: str
    dimensions: str
    changed: bool


def preprocess_image_bytes(
    content: bytes,
    content_type: Optional[str] = None,
    *,
    max_edge: int = 2048,
) -> PreprocessedImage:
    """Auto-rotate, resize, and lightly enhance image bytes for extraction."""

    fallback_mime = _mime_from_content_type(content_type)
    try:
        with Image.open(io.BytesIO(content)) as raw_image:
            original_format = (raw_image.format or "").upper()
            image = ImageOps.exif_transpose(raw_image)
            original_size = image.size
            image = _resize_to_max_edge(image, max_edge=max_edge)
            image = ImageOps.autocontrast(image.convert("RGB"))
            image = ImageEnhance.Sharpness(image).enhance(1.15)
            output = io.BytesIO()
            image.save(output, format="JPEG", quality=88, optimize=True)
            new_content = output.getvalue()
            changed = image.size != original_size or original_format not in {
                "JPEG",
                "JPG",
            }
            return PreprocessedImage(
                content=new_content,
                mime_type="image/jpeg",
                dimensions=f"{image.width}x{image.height}",
                changed=changed,
            )
    except Exception as exc:
        logger.debug("Image preprocessing skipped: %s", exc)
        return PreprocessedImage(
            content=content,
            mime_type=fallback_mime,
            dimensions="unknown",
            changed=False,
        )


def _resize_to_max_edge(image: Image.Image, *, max_edge: int) -> Image.Image:
    width, height = image.size
    largest = max(width, height)
    if largest <= max_edge:
        return image
    scale = max_edge / float(largest)
    new_size = (max(1, int(width * scale)), max(1, int(height * scale)))
    return image.resize(new_size, Image.Resampling.LANCZOS)


def _mime_from_content_type(content_type: Optional[str]) -> str:
    normalized = str(content_type or "").lower()
    if "png" in normalized:
        return "image/png"
    if "gif" in normalized:
        return "image/gif"
    if "webp" in normalized:
        return "image/webp"
    return "image/jpeg"
