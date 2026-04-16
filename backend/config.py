from pathlib import Path


class Config:
    """Application configuration shared by launcher and backend."""

    HOST = "127.0.0.1"
    PORT = 5000
    DEBUG = False

    # Resolve frontend path relative to this file:
    # backend/config.py -> repo root -> frontend
    STATIC_FOLDER = str((Path(__file__).resolve().parents[1] / "frontend"))
