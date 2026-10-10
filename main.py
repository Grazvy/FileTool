#!/usr/bin/env python3
"""File Tool entry point: `python main.py` starts the server and opens the app."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from launcher import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
