"""Atelier web app: a local, single-user web interface over the Atelier engine.

Standard library only (plus openpyxl, which the engine's Excel export needs). The engine package lives in
<repo>/engine and is put on sys.path here so the app always runs against the engine of the same checkout.
"""
import pathlib
import sys

APP_DIR = pathlib.Path(__file__).resolve().parent
REPO_DIR = APP_DIR.parents[1]
ENGINE_DIR = REPO_DIR / "engine"
STATIC_DIR = APP_DIR.parent / "static"

if str(ENGINE_DIR) not in sys.path:
    sys.path.insert(0, str(ENGINE_DIR))

__version__ = "0.1.0"
