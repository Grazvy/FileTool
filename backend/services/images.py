"""Image conversion: PNG <-> JPG and images -> PDF."""

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

# Targets that can hold several images at once, one input per page. Anything else
# is a one-in one-out conversion.
MULTI_TARGETS = (loader.PDF,)


def targets_for(source_fmt: str) -> tuple[str, ...]:
    return CONVERSION_TARGETS.get(source_fmt, ())


def multi_targets_for(source_fmt: str) -> tuple[str, ...]:
    """The targets of targets_for that accept more than one image."""
    return tuple(target for target in targets_for(source_fmt) if target in MULTI_TARGETS)


def convert(data: bytes, source_fmt: str, target_fmt: str) -> bytes:
    """Convert an image blob to target_fmt and return the new bytes."""
    return combine([data], source_fmt, target_fmt)


def combine(datas: list[bytes], source_fmt: str, target_fmt: str) -> bytes:
    """Convert one image, or lay several of them out as the pages of one document."""
    if not datas:
        raise ConversionError("No image was provided.")
    if target_fmt not in targets_for(source_fmt):
        raise ConversionError(f"Cannot convert {source_fmt.upper()} to {target_fmt.upper()}.")
    if len(datas) > 1 and target_fmt not in MULTI_TARGETS:
        raise ConversionError(f"Several images cannot be combined into one {target_fmt.upper()}.")

    opened = [_open(data) for data in datas]
    if target_fmt == loader.PNG:
        return _save(opened[0], "PNG")
    if target_fmt == loader.JPG:
        return _save(_flatten(opened[0]), "JPEG", quality=Config.JPEG_QUALITY)

    pages = [_flatten(image) for image in opened]
    return _save(
        pages[0],
        "PDF",
        resolution=_dpi(opened[0]),
        save_all=True,
        append_images=pages[1:],
    )


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
