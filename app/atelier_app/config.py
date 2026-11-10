"""Settings and their defaults. Nothing host-specific: every path comes from the environment or the user's home.

  ATELIER_DATA_DIR     data directory (default $XDG_DATA_HOME/atelier, else ~/.local/share/atelier)
  ATELIER_PRIVATE_DIR  private calibrations (default <data dir>/private)
  ATELIER_DRAFTING     drafting settings file (default <data dir>/drafting.json; absent: drafting is off)
"""
import json
import os
import pathlib

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8770
MAX_UPLOAD = 5 * 1024 * 1024
LOCAL_USER = "local"  # the only user of a local install; sessions carry it so a multi-user store can key on it


def default_data_dir():
    if os.environ.get("ATELIER_DATA_DIR"):
        return pathlib.Path(os.environ["ATELIER_DATA_DIR"]).expanduser()
    base = os.environ.get("XDG_DATA_HOME") or str(pathlib.Path.home() / ".local" / "share")
    return pathlib.Path(base).expanduser() / "atelier"


def default_private_dir(data_dir):
    if os.environ.get("ATELIER_PRIVATE_DIR"):
        return pathlib.Path(os.environ["ATELIER_PRIVATE_DIR"]).expanduser()
    return pathlib.Path(data_dir) / "private"


def drafting_settings_path(data_dir):
    if os.environ.get("ATELIER_DRAFTING"):
        return pathlib.Path(os.environ["ATELIER_DRAFTING"]).expanduser()
    return pathlib.Path(data_dir) / "drafting.json"


def drafting_settings(data_dir):
    """The drafting settings (see drafting.py). No file: {"backend": "off"}. A bad file also means off, with why."""
    path = drafting_settings_path(data_dir)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"backend": "off"}
    except (OSError, ValueError):
        return {"backend": "off", "problem": "the drafting settings file is not readable JSON"}
    if not isinstance(data, dict):
        return {"backend": "off", "problem": "the drafting settings file must hold a JSON object"}
    if data.get("key_file"):
        data["key_file"] = str(pathlib.Path(data["key_file"]).expanduser())
    return data
