"""Demarrage automatique avec Windows.

On utilise la cle ``HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run`` :
elle ne demande aucun privilege administrateur et se desactive proprement.
L'utilisateur garde la main (le Gestionnaire des taches peut la desactiver).
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Optional

from ..app_paths import is_frozen

log = logging.getLogger(__name__)

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "WallpaperStudio"

#: Argument ajoute pour que le lancement automatique demarre sans fenetre.
MINIMIZED_FLAG = "--minimise"


def _command_line(minimized: bool = True) -> str:
    """Commande a enregistrer, guillemets inclus."""
    if is_frozen():
        target = f'"{Path(sys.executable).resolve()}"'
    else:
        # En developpement, on relance l'interpreteur sur main.py.
        script = Path(__file__).resolve().parent.parent.parent / "main.py"
        target = f'"{Path(sys.executable).resolve()}" "{script}"'
    return f"{target} {MINIMIZED_FLAG}" if minimized else target


def is_enabled() -> bool:
    try:
        import winreg
    except ImportError:  # pragma: no cover
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_READ) as key:
            value, _ = winreg.QueryValueEx(key, VALUE_NAME)
            return bool(value)
    except OSError:
        return False


def current_command() -> Optional[str]:
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_READ) as key:
            value, _ = winreg.QueryValueEx(key, VALUE_NAME)
            return value
    except (ImportError, OSError):
        return None


def enable(minimized: bool = True) -> bool:
    """Active le demarrage automatique. Retourne vrai en cas de succes."""
    try:
        import winreg

        command = _command_line(minimized)
        with winreg.CreateKeyEx(
            winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, command)
        log.info("Demarrage automatique active : %s", command)
        return True
    except (ImportError, OSError) as exc:
        log.error("Activation du demarrage automatique impossible : %s", exc)
        return False


def disable() -> bool:
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.DeleteValue(key, VALUE_NAME)
        log.info("Demarrage automatique desactive")
        return True
    except FileNotFoundError:
        return True  # deja absent
    except (ImportError, OSError) as exc:
        log.error("Desactivation du demarrage automatique impossible : %s", exc)
        return False


def set_enabled(enabled: bool, minimized: bool = True) -> bool:
    return enable(minimized) if enabled else disable()


def refresh_if_needed(minimized: bool = True) -> None:
    """Met a jour la commande si l'executable a ete deplace.

    Sans cela, deplacer le dossier de l'application laisserait une entree de
    demarrage pointant vers un chemin inexistant.
    """
    if not is_enabled():
        return
    expected = _command_line(minimized)
    if current_command() != expected:
        log.info("Mise a jour de la commande de demarrage automatique")
        enable(minimized)
