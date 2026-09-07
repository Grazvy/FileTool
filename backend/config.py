"""Runtime configuration, overridable through FILETOOL_* environment variables."""

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Config:
    """Single source of truth for server settings."""

    HOST = os.environ.get("FILETOOL_HOST", "127.0.0.1")
    PORT = int(os.environ.get("FILETOOL_PORT", "8000"))

    FRONTEND_DIR = Path(os.environ.get("FILETOOL_FRONTEND_DIR", PROJECT_ROOT / "frontend"))

    # Uploads are held in memory only; keep a hard ceiling so a stray file
    # cannot exhaust RAM.
    MAX_UPLOAD_BYTES = int(os.environ.get("FILETOOL_MAX_UPLOAD_BYTES", str(100 * 1024 * 1024)))

    # Resolution used to rasterise PDF pages for the scrollable preview.
    PREVIEW_DPI = int(os.environ.get("FILETOOL_PREVIEW_DPI", "72"))

    # Quality used when writing JPEG output.
    JPEG_QUALITY = int(os.environ.get("FILETOOL_JPEG_QUALITY", "90"))
