"""Filesystem locations Backpack uses.

Two kinds of location, kept apart on purpose.

Writable user data - appdata and appcache. Settings are user data that has to
survive and be backed up; caches are disposable and can grow to hundreds of
megabytes. Every platform draws that line somewhere: on Windows a large cache
under Roaming would be dragged around by a roaming profile, and on macOS the
system may purge ~/Library/Caches on its own, which is fine for tiles and fatal
for settings. Neither function creates the directory: that is up to whoever
writes.

Bundled resources - assets_dir. Read-only files shipped with the app, found by
probing the packaging layout rather than an OS convention. Unlike the
writable-dir helpers it touches the filesystem and raises if the frontend has
not been built.
"""
import os
import sys
from pathlib import Path

from . import APP_NAME


def appdata() -> Path:
    """Directory for settings and anything else worth keeping."""
    match sys.platform:
        case "win32":
            root = os.environ.get("APPDATA", Path.home() / "AppData/Roaming")
        case "darwin":
            root = Path.home() / "Library/Application Support"
        case _:
            root = os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")
    return Path(root) / APP_NAME


def appcache() -> Path:
    """Directory for data that may be deleted at any time."""
    match sys.platform:
        case "win32":
            root = os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local")
        case "darwin":
            root = Path.home() / "Library/Caches"
        case _:
            root = os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")
    return Path(root) / APP_NAME


def assets_dir() -> Path:
    """Locate the bundled assets directory.

    Works both for a normal run (source tree or installed wheel), where
    the directory is looked up in the parents of this file, and for a
    PyInstaller build, where data files are unpacked under sys._MEIPASS.
    """
    base = getattr(sys, "_MEIPASS", None)
    dirs = [Path(base)] if base else Path(__file__).resolve().parents
    for d in dirs:
        assets = d / "assets"
        if (assets / "index.html").is_file():
            return assets
    raise FileNotFoundError("assets not found, run: npm run build")


def app_icon_path(name: str | None = None) -> str | None:
    """Pick a window icon the platform backend can actually decode.

    Windows loads it through System.Drawing.Icon, which reads ICO only.
    Cocoa (NSImage), GTK (GdkPixbuf) and QT (QIcon) all read PNG, while
    SVG needs librsvg or the QT svg plugin and fails on Cocoa.
    """
    if name is None:
        name = "app.ico" if sys.platform == "win32" else "app.png"
    icon = assets_dir() / "icons" / name
    return str(icon) if icon.is_file() else None


def app_settings_path() -> Path:
    """Default path to settings file"""
    return appdata() / "settings.json"