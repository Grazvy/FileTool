import io
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.app import create_app  # noqa: E402


@pytest.fixture
def client():
    return TestClient(create_app())


def make_image(fmt: str, size=(80, 40), color=(200, 40, 40)) -> bytes:
    buffer = io.BytesIO()
    mode = "RGBA" if fmt == "PNG" else "RGB"
    Image.new(mode, size, color + ((255,) if mode == "RGBA" else ())).save(buffer, format=fmt)
    return buffer.getvalue()


@pytest.fixture
def png_bytes() -> bytes:
    return make_image("PNG")


@pytest.fixture
def jpg_bytes() -> bytes:
    return make_image("JPEG")


@pytest.fixture
def pdf_bytes() -> bytes:
    """A three page PDF built from plain colour pages."""
    pages = [Image.new("RGB", (120, 160), color) for color in ("red", "green", "blue")]
    buffer = io.BytesIO()
    pages[0].save(buffer, format="PDF", save_all=True, append_images=pages[1:])
    return buffer.getvalue()
