"""Settings and their defaults. Nothing host-specific: every path comes from the environment or the user's home.

  ATELIER_DATA_DIR     data directory (default $XDG_DATA_HOME/atelier, else ~/.local/share/atelier)
  ATELIER_PRIVATE_DIR  private calibrations (default <data dir>/private)
  ATELIER_SETTINGS     settings file (default <data dir>/settings.json, mode 0600; absent: drafting is off)
  ATELIER_DRAFTING     the iteration 3 drafting file (default <data dir>/drafting.json), read only when there is no
                       settings file
"""
import json
import os
import pathlib

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8770
MAX_UPLOAD = 5 * 1024 * 1024
MAX_DOCUMENT_BODY = 20 * 1024 * 1024 + 256 * 1024  # a 20 MB document plus the multipart envelope
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


def settings_path(data_dir):
    if os.environ.get("ATELIER_SETTINGS"):
        return pathlib.Path(os.environ["ATELIER_SETTINGS"]).expanduser()
    return pathlib.Path(data_dir) / "settings.json"


def settings_mode_problem(path):
    """A warning when the settings file is readable or writable by group or others, else None."""
    try:
        mode = pathlib.Path(path).stat().st_mode
    except OSError:
        return None
    if mode & 0o077:
        return f"the settings file is mode {oct(mode & 0o777)[2:]}; it should be 600 (chmod 600 {path})"
    return None


def save_settings(data_dir, data):
    """Write the settings file atomically, mode 0600."""
    from .storage import atomic_write
    path = settings_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    atomic_write(path, (json.dumps(data, indent=1, ensure_ascii=False) + "\n").encode("utf-8"))
    return path


def drafting_settings(data_dir):
    """The drafting settings (see drafting.normalise). The settings file if there is one, else the iteration 3
    drafting.json, else {"route": "off"}. A bad file also means off, with why. key_file paths are expanded."""
    path = settings_path(data_dir)
    if not path.exists():
        path = drafting_settings_path(data_dir)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"route": "off"}
    except (OSError, ValueError):
        return {"route": "off", "problem": "the settings file is not readable JSON"}
    if not isinstance(data, dict):
        return {"route": "off", "problem": "the settings file must hold a JSON object"}
    for d in (data, data.get("local"), data.get("remote")):
        if isinstance(d, dict) and isinstance(d.get("key_file"), str) and d["key_file"]:
            d["key_file"] = str(pathlib.Path(d["key_file"]).expanduser())
    return data
