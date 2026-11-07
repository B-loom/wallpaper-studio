"""Localisation et initialisation de libVLC.

libVLC est distribue sous licence LGPL v2.1 : l'application s'y lie
dynamiquement, sans modifier la bibliotheque, ce qui autorise sa redistribution
a cote de l'executable (voir ``LICENSES.md``).

La recherche se fait dans cet ordre :

1. dossier ``vlc`` a cote de l'executable (version embarquee, mode portable) ;
2. variable d'environnement ``WALLPAPER_STUDIO_VLC_PATH`` ;
3. installation standard de VLC (Program Files) ;
4. registre Windows (``HKLM\\SOFTWARE\\VideoLAN\\VLC``).

Si rien n'est trouve, :func:`get_vlc_instance` retourne ``None`` et le moteur se
rabat sur Qt Multimedia.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import List, Optional

from ...app_paths import install_dir

log = logging.getLogger(__name__)

_instance = None          # vlc.Instance partagee
_vlc_module = None        # module python-vlc une fois importe
_init_done = False
_init_error: Optional[str] = None
_vlc_dir: Optional[Path] = None
#: Nombre de lecteurs video actuellement en lecture. L'instance libVLC est
#: partagee par toute l'application : elle ne peut etre liberee que lorsque
#: plus aucun lecteur ne s'en sert, quel que soit l'ecran concerne.
_active_players = 0


def _registry_vlc_dir() -> Optional[Path]:
    try:
        import winreg
    except ImportError:  # pragma: no cover - hors Windows
        return None
    for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
            try:
                with winreg.OpenKey(
                    root, r"SOFTWARE\VideoLAN\VLC", 0, winreg.KEY_READ | view
                ) as key:
                    path, _ = winreg.QueryValueEx(key, "InstallDir")
                    p = Path(path)
                    if (p / "libvlc.dll").exists():
                        return p
            except OSError:
                continue
    return None


def candidate_dirs() -> List[Path]:
    """Dossiers ou chercher ``libvlc.dll``, par ordre de priorite."""
    out: List[Path] = []
    out.append(install_dir() / "vlc")
    if getattr(sys, "_MEIPASS", None):
        out.append(Path(sys._MEIPASS) / "vlc")  # noqa: SLF001
    env = os.environ.get("WALLPAPER_STUDIO_VLC_PATH")
    if env:
        out.append(Path(env))
    out.append(Path(r"C:\Program Files\VideoLAN\VLC"))
    out.append(Path(r"C:\Program Files (x86)\VideoLAN\VLC"))
    reg = _registry_vlc_dir()
    if reg:
        out.append(reg)
    return out


def find_vlc_dir() -> Optional[Path]:
    """Premier dossier contenant une ``libvlc.dll`` utilisable."""
    for d in candidate_dirs():
        try:
            if d and (d / "libvlc.dll").exists() and (d / "plugins").is_dir():
                return d
        except OSError:
            continue
    return None


def vlc_directory() -> Optional[Path]:
    return _vlc_dir


def init_vlc() -> bool:
    """Prepare l'environnement puis importe python-vlc. Idempotent."""
    global _vlc_module, _init_done, _init_error, _vlc_dir
    if _init_done:
        return _vlc_module is not None

    _init_done = True
    directory = find_vlc_dir()
    if directory is None:
        _init_error = (
            "libVLC introuvable. Installez VLC 64 bits ou placez un dossier "
            "'vlc' a cote de l'executable."
        )
        log.warning(_init_error)
        return False

    _vlc_dir = directory
    # Ces variables doivent etre posees AVANT l'import de python-vlc, qui
    # charge la DLL au moment de l'import.
    os.environ.setdefault("PYTHON_VLC_LIB_PATH", str(directory / "libvlc.dll"))
    os.environ.setdefault("VLC_PLUGIN_PATH", str(directory / "plugins"))
    if hasattr(os, "add_dll_directory"):
        try:
            os.add_dll_directory(str(directory))
        except OSError:
            pass

    try:
        import vlc  # noqa: PLC0415 - import tardif volontaire
    except Exception as exc:  # noqa: BLE001
        _init_error = f"Chargement de libVLC impossible : {exc}"
        log.warning(_init_error)
        return False

    _vlc_module = vlc
    log.info("libVLC %s chargee depuis %s", vlc.libvlc_get_version().decode(), directory)
    return True


def vlc_module():
    return _vlc_module


def init_error() -> Optional[str]:
    return _init_error


def libvlc_version() -> Optional[str]:
    """Version de libVLC, ou ``None`` si elle n'est pas chargee.

    Ne declenche pas le chargement : voir :func:`ensure_loaded` pour une
    reponse fiable avant toute lecture video.
    """
    if _vlc_module is None:
        return None
    try:
        return _vlc_module.libvlc_get_version().decode("utf-8", "replace")
    except Exception:  # noqa: BLE001
        return None


def ensure_loaded() -> Optional[str]:
    """Charge libVLC si besoin et retourne sa version.

    L'interface doit passer par cette fonction : interroger
    :func:`libvlc_version` avant qu'une video ait ete lue retournerait ``None``
    et laisserait croire a tort que la lecture video est indisponible.
    Le chargement est idempotent et ne coute que quelques dizaines de
    millisecondes la premiere fois.
    """
    init_vlc()
    return libvlc_version()


def _instance_args(hardware_decode: bool) -> List[str]:
    """Options passees a libVLC.

    On desactive tout ce qui n'a pas de sens pour un fond d'ecran : interface,
    statistiques, gestion du clavier, titre affiche a l'ecran.
    """
    import os as _os

    # Un decodeur video ouvre un fil par cœur par defaut. Sur un processeur
    # modeste, deux fils suffisent pour un fond d'ecran et evitent autant de
    # piles et de tampons en memoire.
    coeurs = _os.cpu_count() or 2
    threads = max(1, min(2, coeurs // 2))

    args = [
        "--no-video-title-show",
        "--no-snapshot-preview",
        "--no-stats",
        "--no-sub-autodetect-file",
        "--no-osd",
        "--quiet",
        "--intf", "dummy",
        "--no-spu",
        # Un fond d'ecran ne doit jamais capter le clavier ou la souris.
        "--no-keyboard-events",
        "--no-mouse-events",
        # Tampon d'entree reduit : un fichier local n'a pas besoin d'une
        # seconde d'avance, et cela economise plusieurs dizaines de Mo.
        "--file-caching=300",
        "--live-caching=300",
        "--disc-caching=300",
        f"--avcodec-threads={threads}",
        # Services inutiles a un fond d'ecran.
        "--no-lua",
        "--no-interact",
        "--no-video-on-top",
        "--no-snapshot-preview",
    ]
    # Le decodage materiel soulage nettement un processeur modeste.
    args.append("--avcodec-hw=any" if hardware_decode else "--avcodec-hw=none")
    return args


def get_vlc_instance(hardware_decode: bool = True):
    """Instance libVLC partagee par tous les lecteurs. ``None`` si indisponible.

    Une seule instance pour toute l'application : chaque instance charge le
    catalogue de greffons (plusieurs dizaines de megaoctets), ce qui serait
    gaspille par ecran.
    """
    global _instance
    if _instance is not None:
        return _instance
    if not init_vlc():
        return None
    try:
        _instance = _vlc_module.Instance(_instance_args(hardware_decode))
    except Exception as exc:  # noqa: BLE001
        log.error("Creation de l'instance libVLC impossible : %s", exc)
        return None
    if _instance is None:
        log.error("libVLC a refuse de creer une instance (options rejetees ?)")
    return _instance


def instance_is_loaded() -> bool:
    """Vrai si une instance libVLC occupe actuellement de la memoire."""
    return _instance is not None


def register_player() -> None:
    """Signale qu'un lecteur video commence a utiliser l'instance partagee."""
    global _active_players
    _active_players += 1


def unregister_player() -> None:
    """Signale qu'un lecteur video a libere l'instance partagee."""
    global _active_players
    _active_players = max(0, _active_players - 1)


def active_players() -> int:
    return _active_players


def release_vlc_instance(force: bool = False) -> bool:
    """Libere l'instance partagee si plus aucun lecteur ne l'utilise.

    Retourne vrai si la liberation a eu lieu. ``force`` ne sert qu'a
    l'extinction de l'application, une fois tous les lecteurs arretes :
    liberer l'instance pendant une lecture ferait planter libVLC.
    """
    global _instance
    if _active_players > 0 and not force:
        log.debug(
            "Liberation de libVLC differee : %s lecteur(s) encore actif(s)",
            _active_players,
        )
        return False
    if _instance is not None:
        try:
            _instance.release()
        except Exception:  # noqa: BLE001
            pass
        _instance = None
        return True
    return False
