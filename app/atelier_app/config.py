"""Settings and their defaults. Nothing host-specific: every path comes from the environment or the user's home.

  ATELIER_DATA_DIR     data directory (default $XDG_DATA_HOME/atelier, else ~/.local/share/atelier)
  ATELIER_PRIVATE_DIR  private calibrations (default <data dir>/private)
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


def default_private_dir(data_dir):
    if os.environ.get("ATELIER_PRIVATE_DIR"):
        return pathlib.Path(os.environ["ATELIER_PRIVATE_DIR"]).expanduser()
    return pathlib.Path(data_dir) / "private"
