import base64
import hashlib
import io
from typing import Tuple

from PIL import Image, ImageStat


def decode_data_url(value: str) -> Image.Image:
    """Decode a base64 data URL (or raw base64) into a normalized RGB image."""
    if not value:
        raise ValueError("image_base64 is required")
    payload = value.split(",", 1)[1] if "," in value else value
    try:
        raw = base64.b64decode(payload, validate=True)
        image = Image.open(io.BytesIO(raw))
        image.load()
        return image.convert("RGB")
    except Exception as exc:
        raise ValueError("Invalid base64 image") from exc


def image_fingerprint(image: Image.Image, size: Tuple[int, int] = (16, 16)) -> str:
    """Perceptual-ish hash suitable for avoiding repeat OCR on nearly identical frames."""
    thumb = image.convert("L").resize(size)
    pixels = list(thumb.getdata())
    mean = sum(pixels) / len(pixels)
    bits = "".join("1" if pixel >= mean else "0" for pixel in pixels)
    return hashlib.sha256(bits.encode()).hexdigest()[:24]


def image_quality(image: Image.Image) -> dict:
    gray = image.convert("L")
    stat = ImageStat.Stat(gray)
    brightness = stat.mean[0]
    # Variance is a cheap CPU-only sharpness signal; browser performs the primary check.
    variance = stat.var[0]
    return {
        "brightness": round(brightness, 2),
        "contrast": round(variance ** 0.5, 2),
        "acceptable": 35 <= brightness <= 225 and variance >= 20,
    }
