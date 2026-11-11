"""Settings and their defaults. Nothing host-specific: every path comes from the environment or the user's home.

  ATELIER_DATA_DIR     data directory (default $XDG_DATA_HOME/atelier, else ~/.local/share/atelier)
"""
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
