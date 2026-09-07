"""FastAPI application: serves the API and the static frontend from one process."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.api.routes import router
from backend.config import Config
from backend.errors import FileToolError


def create_app() -> FastAPI:
    app = FastAPI(title="File Tool", version="0.1.0", docs_url=None, redoc_url=None)
    app.include_router(router)

    @app.exception_handler(FileToolError)
    async def handle_file_tool_error(_: Request, exc: FileToolError) -> JSONResponse:
        """Bad input is a client error, never a stack trace."""
        return JSONResponse(status_code=400, content={"error": str(exc)})

    if Config.FRONTEND_DIR.is_dir():
        app.mount("/", StaticFiles(directory=Config.FRONTEND_DIR, html=True), name="frontend")

    return app


app = create_app()
