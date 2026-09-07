"""API routes. Every request carries its own file: the server keeps no state."""

import base64
from pathlib import Path

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import Response

from backend.config import Config
from backend.errors import UploadTooLargeError
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
async def convert(file: UploadFile = File(...), target: str = Form(...)) -> Response:
    """Convert an image to another format and stream the result back."""
    data = await _read(file)
    source_fmt = loader.detect_format(data)
    target_fmt = target.strip().lower()
    converted = images.convert(data, source_fmt, target_fmt)
    return _download(converted, target_fmt, _stem(file.filename, source_fmt))


@router.post("/pdf/remove-pages")
async def remove_pages(
    file: UploadFile = File(...),
    pages: list[int] = Form(default=[]),
) -> Response:
    """Return the uploaded PDF without the given zero based page indices."""
    data = await _read(file)
    loader.detect_format(data)  # rejects anything that is not a supported input
    result = pdf.remove_pages(data, pages)
    return _download(result, loader.PDF, _stem(file.filename, loader.PDF))


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
