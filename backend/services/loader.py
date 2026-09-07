"""Input loading: decide what an uploaded blob actually is, and reject the rest.

The format is detected from the file's magic bytes rather than from its name or
the browser supplied content type, so a renamed file cannot slip through.
"""

from backend.errors import UnsupportedFormatError

PDF = "pdf"
PNG = "png"
JPG = "jpg"

SUPPORTED_INPUTS = (PDF, PNG, JPG)

MEDIA_TYPES = {
    PDF: "application/pdf",
    PNG: "image/png",
    JPG: "image/jpeg",
}

EXTENSIONS = {
    PDF: ".pdf",
    PNG: ".png",
    JPG: ".jpg",
}

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_JPG_MAGIC = b"\xff\xd8\xff"
_PDF_MAGIC = b"%PDF-"


def detect_format(data: bytes) -> str:
    """Return one of SUPPORTED_INPUTS, or raise UnsupportedFormatError."""
    if data.startswith(_PDF_MAGIC):
        return PDF
    if data.startswith(_PNG_MAGIC):
        return PNG
    if data.startswith(_JPG_MAGIC):
        return JPG
    raise UnsupportedFormatError("Only PDF, PNG and JPG files are supported.")


def media_type(fmt: str) -> str:
    return MEDIA_TYPES[fmt]


def extension(fmt: str) -> str:
    return EXTENSIONS[fmt]
