"""API routes. Every request carries its own file: the server keeps no state."""

import base64
from pathlib import Path

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import Response

from backend.config import Config
from backend.errors import PdfError, UnsupportedFormatError, UploadTooLargeError
from backend.services import images, loader, pdf

router = APIRouter(prefix="/api")


@router.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@router.post("/load")
async def load(file: UploadFile = File(...)) -> dict:
    """Identify an upload and describe what can be done with it.

    PDFs come back with a rendered preview of every page; images come back with
    the list of conversion targets.
    """
    data = await _read(file)
    fmt = loader.detect_format(data)

    result = {
        "format": fmt,
        "name": _safe_name(file.filename, fmt),
        "size": len(data),
        "targets": list(images.targets_for(fmt)),
        "multi_targets": list(images.multi_targets_for(fmt)),
        "pages": [],
    }
    if fmt == loader.PDF:
        result["pages"] = [
            {
                "index": page.index,
                "width": page.width,
                "height": page.height,
                "image": "data:image/png;base64," + base64.b64encode(page.png).decode(),
            }
            for page in pdf.render_previews(data)
        ]
    return result


@router.post("/convert")
async def convert(file: list[UploadFile] = File(...), target: str = Form(...)) -> Response:
    """Convert an image, or combine several of one format, into the target format.

    Files are combined in the order they were uploaded, one image per page.
    """
    datas = [await _read(upload) for upload in file]
    source_fmt = _one_format(datas)
    target_fmt = target.strip().lower()
    converted = images.combine(datas, source_fmt, target_fmt)
    return _download(converted, target_fmt, _stem(file[0].filename, source_fmt))


@router.post("/image/crop")
async def crop(
    file: UploadFile = File(...),
    left: float = Form(...),
    top: float = Form(...),
    right: float = Form(...),
    bottom: float = Form(...),
) -> Response:
    """Cut the given rectangle out of one image, keeping its format.

    The rectangle is expressed as fractions of the image, so the client works
    from what it displays and never needs the original pixel size.
    """
    data = await _read(file)
    fmt = loader.detect_format(data)
    if fmt == loader.PDF:
        raise UnsupportedFormatError("Only PNG and JPG files can be cropped.")
    result = images.crop(data, fmt, (left, top, right, bottom))
    return _download(result, fmt, _stem(file.filename, fmt))


@router.post("/pdf/compose")
async def compose(
    file: list[UploadFile] = File(...),
    pages: list[str] = Form(default=[]),
) -> Response:
    """Build one PDF from the uploaded PDFs, taking the pages named by `pages`.

    A page is written as `document:page`, both zero based, and the order of the
    list is the order of the result — so merging, removing and reordering are all
    the same request.
    """
    datas = [await _read(upload) for upload in file]
    if _one_format(datas) != loader.PDF:
        raise UnsupportedFormatError("Only PDF files can be merged into a PDF.")
    result = pdf.compose(datas, _page_refs(pages))
    return _download(result, loader.PDF, _stem(file[0].filename, loader.PDF))


def _one_format(datas: list[bytes]) -> str:
    """Detect the format of every upload and require them all to be the same."""
    if not datas:
        raise UnsupportedFormatError("No file was uploaded.")
    formats = {loader.detect_format(data) for data in datas}
    if len(formats) > 1:
        raise UnsupportedFormatError("All files must have the same format.")
    return formats.pop()


def _page_refs(values: list[str]) -> list[tuple[int, int]]:
    refs = []
    for value in values:
        document, _, index = value.partition(":")
        try:
            refs.append((int(document), int(index)))
        except ValueError:
            raise PdfError(f'"{value}" is not a document:page reference.') from None
    return refs


async def _read(file: UploadFile) -> bytes:
    data = await file.read()
    if len(data) > Config.MAX_UPLOAD_BYTES:
        limit_mb = Config.MAX_UPLOAD_BYTES // (1024 * 1024)
        raise UploadTooLargeError(f"The file is larger than the {limit_mb} MB limit.")
    return data


def _stem(filename: str | None, fmt: str) -> str:
    return Path(_safe_name(filename, fmt)).stem


def _safe_name(filename: str | None, fmt: str) -> str:
    """Keep only the base name of a client supplied path, with a sane fallback.

    The name ends up in a Content-Disposition header, so quotes, control
    characters and anything non ASCII are dropped rather than escaped.
    """
    name = Path(filename or "").name
    name = "".join(char for char in name if char.isascii() and char.isprintable())
    name = name.replace('"', "").replace("\\", "").strip()
    return name or f"file{loader.extension(fmt)}"


def _download(data: bytes, fmt: str, stem: str) -> Response:
    filename = f"{stem}{loader.extension(fmt)}"
    return Response(
        content=data,
        media_type=loader.media_type(fmt),
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
