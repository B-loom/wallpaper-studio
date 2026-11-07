"""Etat d'alimentation et de session Windows.

Permet de reduire la consommation sur batterie et de suspendre les rendus quand
la session est verrouillee ou l'ecran eteint.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wintypes
import logging
from dataclasses import dataclass
from typing import Optional

log = logging.getLogger(__name__)

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
user32 = ctypes.WinDLL("user32", use_last_error=True)

AC_LINE_OFFLINE = 0
AC_LINE_ONLINE = 1
AC_LINE_UNKNOWN = 255

BATTERY_FLAG_NO_BATTERY = 128
BATTERY_PERCENT_UNKNOWN = 255


class SYSTEM_POWER_STATUS(ctypes.Structure):
    _fields_ = [
        ("ACLineStatus", wintypes.BYTE),
        ("BatteryFlag", wintypes.BYTE),
        ("BatteryLifePercent", wintypes.BYTE),
        ("SystemStatusFlag", wintypes.BYTE),
        ("BatteryLifeTime", wintypes.DWORD),
        ("BatteryFullLifeTime", wintypes.DWORD),
    ]


@dataclass(frozen=True)
class PowerStatus:
    """Etat d'alimentation, tel que mesure (jamais devine)."""

    has_battery: bool
    on_battery: bool
    #: Pourcentage restant, ou ``None`` si indisponible.
    percent: Optional[int]

    @property
    def description(self) -> str:
        if not self.has_battery:
            return "Secteur (pas de batterie)"
        source = "Batterie" if self.on_battery else "Secteur"
        if self.percent is None:
            return source
        return f"{source} - {self.percent} %"


def power_status() -> PowerStatus:
    """Releve l'etat d'alimentation du systeme."""
    status = SYSTEM_POWER_STATUS()
    if not kernel32.GetSystemPowerStatus(ctypes.byref(status)):
        return PowerStatus(has_battery=False, on_battery=False, percent=None)

    flag = status.BatteryFlag & 0xFF
    has_battery = not bool(flag & BATTERY_FLAG_NO_BATTERY) and flag != 0xFF
    ac = status.ACLineStatus & 0xFF
    percent_raw = status.BatteryLifePercent & 0xFF
    percent = None if percent_raw == BATTERY_PERCENT_UNKNOWN else int(percent_raw)

    return PowerStatus(
        has_battery=has_battery,
        on_battery=has_battery and ac == AC_LINE_OFFLINE,
        percent=percent,
    )


def is_on_battery() -> bool:
    return power_status().on_battery


def is_session_locked() -> bool:
    """Vrai si la session est verrouillee (bureau securise affiche).

    On compare le bureau d'entree au bureau courant : lorsqu'une session est
    verrouillee, l'Explorateur n'a plus acces au bureau ``Default``.
    """
    DESKTOP_SWITCHDESKTOP = 0x0100
    handle = user32.OpenInputDesktop(0, False, DESKTOP_SWITCHDESKTOP)
    if not handle:
        # Pas d'acces au bureau d'entree : session verrouillee ou ecran de
        # connexion actif.
        return True
    user32.CloseDesktop(handle)
    return False


def is_display_on() -> bool:
    """Vrai si l'ecran est allume, autant que Windows le laisse savoir.

    Windows n'expose cette information que via une notification
    (``RegisterPowerSettingNotification``). En son absence, on retourne ``True``
    plutot que de supposer l'ecran eteint, ce qui couperait les fonds a tort.
    """
    return True
