"""PDF services: rasterise pages for preview and drop pages from a document."""

import io

import pypdfium2 as pdfium
from pypdf import PdfReader, PdfWriter
from pypdf.errors import PdfReadError

from backend.config import Config
from backend.errors import PdfError


class PagePreview:
    """One rendered page: PNG bytes plus the pixel size of that render."""

    __slots__ = ("index", "png", "width", "height")

    def __init__(self, index: int, png: bytes, width: int, height: int):
        self.index = index
        self.png = png
        self.width = width
        self.height = height


def page_count(data: bytes) -> int:
    document = _open(data)
    try:
        return len(document)
    finally:
        document.close()


def render_previews(data: bytes, dpi: int | None = None) -> list[PagePreview]:
    """Render every page to a PNG at Config.PREVIEW_DPI (or the given dpi)."""
    scale = (dpi or Config.PREVIEW_DPI) / 72.0
    document = _open(data)
    try:
        previews = []
        for index in range(len(document)):
            page = document[index]
            try:
                image = page.render(scale=scale).to_pil()
            finally:
                page.close()
            buffer = io.BytesIO()
            image.save(buffer, format="PNG")
            previews.append(PagePreview(index, buffer.getvalue(), image.width, image.height))
        return previews
    finally:
        document.close()


def remove_pages(data: bytes, indices: list[int]) -> bytes:
    """Return the document without the given zero based page indices."""
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise PdfError("Encrypted PDFs are not supported.")
        total = len(reader.pages)
    except PdfReadError as exc:
        raise PdfError("The PDF could not be read.") from exc

    dropped = set(indices)
    for index in dropped:
        if not 0 <= index < total:
            raise PdfError(f"Page {index + 1} does not exist in a {total} page document.")
    if len(dropped) == total:
        raise PdfError("A PDF must keep at least one page.")

    writer = PdfWriter()
    for index, page in enumerate(reader.pages):
        if index not in dropped:
            writer.add_page(page)

    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def _open(data: bytes) -> pdfium.PdfDocument:
    try:
        return pdfium.PdfDocument(data)
    except pdfium.PdfiumError as exc:
        raise PdfError("The PDF could not be read.") from exc
