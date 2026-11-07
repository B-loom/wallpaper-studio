"""Restitution de la memoire inutilisee au systeme.

Pourquoi ce module
------------------
Liberer des objets Python ou Qt ne rend pas forcement la memoire a Windows :
les allocateurs la conservent dans leurs tas pour la reutiliser. Le processus
continue donc d'apparaitre volumineux dans le Gestionnaire des taches, et les
pages restent comptees contre la memoire disponible de la machine.

``SetProcessWorkingSetSize`` avec ``-1, -1`` demande a Windows de reduire le
jeu de travail du processus : les pages reellement inutilisees repartent vers
le fichier d'echange ou la liste des pages libres.

Quand l'utiliser
----------------
Uniquement lors des transitions vers un etat de repos : fenetre fermee dans la
zone de notification, liberation de libVLC, passage en pause automatique. Le
faire en continu serait contre-productif, car les pages encore utiles seraient
rechargees depuis le disque au prochain acces.
"""

from __future__ import annotations

import ctypes
import gc
import logging
import os
from typing import Optional

log = logging.getLogger(__name__)

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
psapi = ctypes.WinDLL("psapi", use_last_error=True)

SIZE_T = ctypes.c_size_t
kernel32.SetProcessWorkingSetSize.argtypes = [ctypes.c_void_p, SIZE_T, SIZE_T]
kernel32.SetProcessWorkingSetSize.restype = ctypes.c_bool

try:  # psutil n'est pas indispensable au fonctionnement
    import psutil

    _process: Optional["psutil.Process"] = psutil.Process(os.getpid())
except Exception:  # noqa: BLE001
    _process = None


def current_rss_mb() -> Optional[float]:
    """Memoire de travail du processus en mega-octets, si mesurable."""
    if _process is None:
        return None
    try:
        return _process.memory_info().rss / (1024 * 1024)
    except Exception:  # noqa: BLE001
        return None


def trim_working_set(reason: str = "") -> Optional[float]:
    """Rend au systeme la memoire que l'application n'utilise plus.

    Retourne le nombre de mega-octets liberes, ou ``None`` si la mesure n'est
    pas disponible. L'operation est sans danger : Windows recharge a la
    demande les pages dont le processus aurait de nouveau besoin.
    """
    gc.collect()
    avant = current_rss_mb()

    try:
        handle = kernel32.GetCurrentProcess()
        ok = kernel32.SetProcessWorkingSetSize(handle, SIZE_T(-1), SIZE_T(-1))
    except Exception as exc:  # noqa: BLE001
        log.debug("Reduction du jeu de travail impossible : %s", exc)
        return None
    if not ok:
        log.debug("SetProcessWorkingSetSize a echoue (erreur %s)",
                  ctypes.get_last_error())
        return None

    apres = current_rss_mb()
    if avant is None or apres is None:
        log.debug("Jeu de travail reduit%s", f" ({reason})" if reason else "")
        return None

    libere = avant - apres
    log.info(
        "Memoire rendue au systeme : %.0f Mo (%.0f -> %.0f Mo)%s",
        libere, avant, apres, f" - {reason}" if reason else "",
    )
    return libere
