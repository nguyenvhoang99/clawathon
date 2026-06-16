from __future__ import annotations

import base64
import io

from PIL import Image

THUMBNAIL_MAX_PX = 200
THUMBNAIL_JPEG_QUALITY = 75


def make_thumbnail_base64(raw: bytes, max_size: int = THUMBNAIL_MAX_PX) -> str:
    """Resize receipt image to a JPEG thumbnail for session storage."""
    img = Image.open(io.BytesIO(raw))
    img.thumbnail((max_size, max_size))
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=THUMBNAIL_JPEG_QUALITY)
    return base64.b64encode(buf.getvalue()).decode("ascii")
