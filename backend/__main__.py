"""Run the backend directly: `python -m backend`.

The packaged launcher (browser opening, shutdown handling) lives elsewhere; this
entry point exists so the server can be started on its own during development.
"""

import uvicorn

from backend.config import Config

if __name__ == "__main__":
    uvicorn.run("backend.app:app", host=Config.HOST, port=Config.PORT)
