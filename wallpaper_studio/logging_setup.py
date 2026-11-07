r"""Configuration des journaux.

Un fichier tournant dans %LOCALAPPDATA%\WallpaperStudio\logs plus la
console lorsqu'elle existe. Les exceptions non rattrapees sont journalisees afin
qu'un plantage en arriere-plan laisse une trace exploitable.
"""

from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path

from .app_paths import log_dir

_FORMAT = "%(asctime)s %(levelname)-7s [%(name)s] %(message)s"
_configured = False


def setup_logging(level: int = logging.INFO, filename: str = "wallpaper-studio.log") -> Path:
    """Installe les gestionnaires de journalisation. Idempotent."""
    global _configured
    path = log_dir() / filename
    if _configured:
        return path

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    fmt = logging.Formatter(_FORMAT, datefmt="%Y-%m-%d %H:%M:%S")

    fh = logging.handlers.RotatingFileHandler(
        path, maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    root.addHandler(fh)

    # En mode fenetre (PyInstaller --windowed) stdout peut etre None.
    if sys.stderr is not None:
        sh = logging.StreamHandler(sys.stderr)
        sh.setLevel(level)
        sh.setFormatter(fmt)
        root.addHandler(sh)

    # Moins de bruit venant des bibliotheques tierces.
    logging.getLogger("PIL").setLevel(logging.WARNING)

    def _hook(exc_type, exc, tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc, tb)
            return
        root.critical("Exception non rattrapee", exc_info=(exc_type, exc, tb))

    sys.excepthook = _hook
    _configured = True
    root.info("Journalisation initialisee -> %s", path)
    return path


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
