"""MYRA local data paths.

Personal data deliberately lives outside the source/install folder so an
application update or uninstall does not erase conversations, memories or
notes.  Set ``MYRA_DATA_DIR`` to override the platform default (tests use
this to keep every test database in a temporary directory).
"""
import os
from pathlib import Path


def data_dir(create=True):
    configured = os.environ.get("MYRA_DATA_DIR", "").strip()
    if configured:
        path = Path(configured).expanduser()
    elif os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        path = Path(base) / "MYRA"
    elif os.uname().sysname == "Darwin" if hasattr(os, "uname") else False:
        path = Path.home() / "Library" / "Application Support" / "MYRA"
    else:
        base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
        path = Path(base) / "MYRA"
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def database_path(create=True):
    return data_dir(create=create) / "myra.db"


def workspace_dir(create=True):
    """The only folder built-in file skills may read/write by default."""
    path = data_dir(create=create) / "workspace"
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def models_dir(create=True):
    path = data_dir(create=create) / "models"
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path
