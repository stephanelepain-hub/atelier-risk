#!/usr/bin/env python3
"""Start the Atelier web app: python3 app/serve.py (see docs/app.md)."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from atelier_app.server import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
