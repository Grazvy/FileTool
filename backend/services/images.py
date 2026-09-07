"""Image conversion: PNG <-> JPG and image -> single page PDF."""

import io

from PIL import Image, UnidentifiedImageError

from backend.config import Config
from backend.errors import ConversionError
from backend.services import loader

# Conversions offered per input format. The frontend renders exactly this map.
CONVERSION_TARGETS = {
    loader.PNG: (loader.JPG, loader.PDF),
    loader.JPG: (loader.PNG, loader.PDF),
    loader.PDF: (),
}


def targets_for(source_fmt: str) -> tuple[str, ...]:
    return CONVERSION_TARGETS.get(source_fmt, ())


def convert(data: bytes, source_fmt: str, target_fmt: str) -> bytes:
    """Convert an image blob to target_fmt and return the new bytes."""
    if target_fmt not in targets_for(source_fmt):
        raise ConversionError(f"Cannot convert {source_fmt.upper()} to {target_fmt.upper()}.")

    image = _open(data)
    if target_fmt == loader.PNG:
        return _save(image, "PNG")
    if target_fmt == loader.JPG:
        return _save(_flatten(image), "JPEG", quality=Config.JPEG_QUALITY)
    return _save(_flatten(image), "PDF", resolution=_dpi(image))


def _open(data: bytes) -> Image.Image:
    try:
        image = Image.open(io.BytesIO(data))
        image.load()
    except (UnidentifiedImageError, OSError) as exc:
        raise ConversionError("The image could not be read.") from exc
    return image


def _flatten(image: Image.Image) -> Image.Image:
    """Drop transparency onto a white background; JPEG and PDF have no alpha."""
    if image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info):
        rgba = image.convert("RGBA")
        background = Image.new("RGB", rgba.size, (255, 255, 255))
        background.paste(rgba, mask=rgba.split()[-1])
        return background
    if image.mode != "RGB":
        return image.convert("RGB")
    return image


def _dpi(image: Image.Image) -> float:
    """Use the image's own DPI so a PDF page keeps its physical size."""
    dpi = image.info.get("dpi")
    if isinstance(dpi, (tuple, list)) and dpi and 1 <= float(dpi[0]) <= 2400:
        return float(dpi[0])
    return 72.0


def _save(image: Image.Image, pillow_format: str, **options) -> bytes:
    buffer = io.BytesIO()
    try:
        image.save(buffer, format=pillow_format, **options)
    except OSError as exc:
        raise ConversionError(f"Writing {pillow_format} output failed.") from exc
    return buffer.getvalue()
