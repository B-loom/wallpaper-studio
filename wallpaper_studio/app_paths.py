r"""Emplacements de fichiers de l'application.

Toutes les donnees mutables vivent dans %LOCALAPPDATA%\WallpaperStudio afin
que l'application fonctionne aussi depuis un dossier en lecture seule (version
portable installee dans Program Files, par exemple).

Si un fichier ``portable.txt`` existe a cote de l'executable, les donnees sont
stockees dans un sous-dossier ``data`` local : c'est le mode portable.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from . import APP_ID

_PORTABLE_MARKER = "portable.txt"


def is_frozen() -> bool:
    """Vrai lorsque l'application tourne depuis un bundle PyInstaller."""
    return getattr(sys, "frozen", False)


def install_dir() -> Path:
    """Dossier contenant l'executable (ou la racine du depot en developpement)."""
    if is_frozen():
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def resource_dir() -> Path:
    """Dossier des ressources embarquees (icones, modeles web, presets)."""
    if is_frozen():
        base = getattr(sys, "_MEIPASS", None)
        if base:
            return Path(base) / "resources"
    return Path(__file__).resolve().parent.parent / "resources"


def is_portable() -> bool:
    return (install_dir() / _PORTABLE_MARKER).exists()


def data_dir() -> Path:
    """Dossier racine des donnees utilisateur."""
    if is_portable():
        root = install_dir() / "data"
    else:
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        root = Path(base) / APP_ID
    root.mkdir(parents=True, exist_ok=True)
    return root


def _sub(name: str) -> Path:
    p = data_dir() / name
    p.mkdir(parents=True, exist_ok=True)
    return p


def config_dir() -> Path:
    return _sub("config")


def log_dir() -> Path:
    return _sub("logs")


def cache_dir() -> Path:
    return _sub("cache")


def thumbnail_dir() -> Path:
    return _sub("thumbnails")


def library_dir() -> Path:
    """Dossier par defaut quand l'utilisateur choisit de copier ses medias."""
    return _sub("library")


def web_wallpaper_dir() -> Path:
    """Fonds d'ecran HTML installes par l'utilisateur."""
    return _sub("web")


def database_path() -> Path:
    return data_dir() / "wallpaper-studio.db"


def settings_path() -> Path:
    return config_dir() / "settings.json"


def lock_path() -> Path:
    return data_dir() / "instance.lock"
