"""Enumeration des moniteurs et detection des changements de configuration.

Chaque moniteur recoit une *cle stable* (:attr:`MonitorInfo.key`) deduite de
l'identifiant materiel renvoye par ``EnumDisplayDevicesW``. Contrairement au nom
de peripherique (``\\\\.\\DISPLAY1``), cette cle survit a un debranchement puis
rebranchement : elle permet de restaurer la configuration du bon ecran.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wintypes
import hashlib
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

user32 = ctypes.WinDLL("user32", use_last_error=True)

MONITORINFOF_PRIMARY = 0x00000001
EDD_GET_DEVICE_INTERFACE_NAME = 0x00000001
ENUM_CURRENT_SETTINGS = -1

MDT_EFFECTIVE_DPI = 0

ORIENTATION_LANDSCAPE = "paysage"
ORIENTATION_PORTRAIT = "portrait"


class MONITORINFOEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT),
        ("dwFlags", wintypes.DWORD),
        ("szDevice", wintypes.WCHAR * 32),
    ]


class DISPLAY_DEVICEW(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("DeviceName", wintypes.WCHAR * 32),
        ("DeviceString", wintypes.WCHAR * 128),
        ("StateFlags", wintypes.DWORD),
        ("DeviceID", wintypes.WCHAR * 128),
        ("DeviceKey", wintypes.WCHAR * 128),
    ]


class DEVMODEW(ctypes.Structure):
    _fields_ = [
        ("dmDeviceName", wintypes.WCHAR * 32),
        ("dmSpecVersion", wintypes.WORD),
        ("dmDriverVersion", wintypes.WORD),
        ("dmSize", wintypes.WORD),
        ("dmDriverExtra", wintypes.WORD),
        ("dmFields", wintypes.DWORD),
        ("dmPositionX", ctypes.c_long),
        ("dmPositionY", ctypes.c_long),
        ("dmDisplayOrientation", wintypes.DWORD),
        ("dmDisplayFixedOutput", wintypes.DWORD),
        ("dmColor", ctypes.c_short),
        ("dmDuplex", ctypes.c_short),
        ("dmYResolution", ctypes.c_short),
        ("dmTTOption", ctypes.c_short),
        ("dmCollate", ctypes.c_short),
        ("dmFormName", wintypes.WCHAR * 32),
        ("dmLogPixels", wintypes.WORD),
        ("dmBitsPerPel", wintypes.DWORD),
        ("dmPelsWidth", wintypes.DWORD),
        ("dmPelsHeight", wintypes.DWORD),
        ("dmDisplayFlags", wintypes.DWORD),
        ("dmDisplayFrequency", wintypes.DWORD),
        ("dmICMMethod", wintypes.DWORD),
        ("dmICMIntent", wintypes.DWORD),
        ("dmMediaType", wintypes.DWORD),
        ("dmDitherType", wintypes.DWORD),
        ("dmReserved1", wintypes.DWORD),
        ("dmReserved2", wintypes.DWORD),
        ("dmPanningWidth", wintypes.DWORD),
        ("dmPanningHeight", wintypes.DWORD),
    ]


MONITORENUMPROC = ctypes.WINFUNCTYPE(
    wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC,
    ctypes.POINTER(wintypes.RECT), wintypes.LPARAM,
)

user32.EnumDisplayMonitors.argtypes = [
    wintypes.HDC, ctypes.POINTER(wintypes.RECT), MONITORENUMPROC, wintypes.LPARAM,
]
user32.EnumDisplayMonitors.restype = wintypes.BOOL
user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(MONITORINFOEXW)]
user32.GetMonitorInfoW.restype = wintypes.BOOL
user32.EnumDisplayDevicesW.argtypes = [
    wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(DISPLAY_DEVICEW), wintypes.DWORD,
]
user32.EnumDisplayDevicesW.restype = wintypes.BOOL
user32.EnumDisplaySettingsW.argtypes = [
    wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(DEVMODEW),
]
user32.EnumDisplaySettingsW.restype = wintypes.BOOL


@dataclass(frozen=True)
class MonitorInfo:
    """Description d'un moniteur connecte."""

    #: Cle stable entre deux sessions et resistante au rebranchement.
    key: str
    #: Nom de peripherique Windows, par exemple ``\\\\.\\DISPLAY1``.
    device: str
    #: Libelle lisible, par exemple ``Ecran PnP generique``.
    name: str
    #: Rectangle ecran : (x, y, largeur, hauteur). x/y peuvent etre negatifs.
    rect: Tuple[int, int, int, int]
    #: Zone de travail (hors barre des taches), meme format.
    work_rect: Tuple[int, int, int, int]
    is_primary: bool
    dpi: int = 96
    refresh_hz: int = 0
    orientation: str = ORIENTATION_LANDSCAPE
    #: Index d'enumeration, utile pour un libelle court du type ``Ecran 1``.
    index: int = 0

    @property
    def width(self) -> int:
        return self.rect[2]

    @property
    def height(self) -> int:
        return self.rect[3]

    @property
    def scale(self) -> float:
        return self.dpi / 96.0

    @property
    def label(self) -> str:
        suffix = " (principal)" if self.is_primary else ""
        return f"Ecran {self.index + 1}{suffix}"

    @property
    def resolution_text(self) -> str:
        return f"{self.width} x {self.height}"

    def describe(self) -> str:
        return (
            f"{self.label} - {self.name} - {self.resolution_text}"
            f" @ {self.refresh_hz} Hz - {self.orientation}"
        )


def _monitor_hardware_key(device: str, fallback: str) -> str:
    """Cle stable deduite de l'identifiant materiel de l'ecran.

    ``DeviceID`` contient l'identifiant PnP du moniteur (p. ex.
    ``MONITOR\\BOE0A1B\\{...}\\0003``). On le hache pour obtenir une cle courte
    et utilisable comme identifiant en base.
    """
    dd = DISPLAY_DEVICEW()
    dd.cb = ctypes.sizeof(dd)
    if user32.EnumDisplayDevicesW(device, 0, ctypes.byref(dd),
                                  EDD_GET_DEVICE_INTERFACE_NAME):
        raw = dd.DeviceID or dd.DeviceKey
        if raw:
            digest = hashlib.sha1(raw.encode("utf-8", "replace")).hexdigest()[:16]
            return f"mon_{digest}"
    # Dernier recours : le nom de peripherique. Moins stable mais toujours defini.
    digest = hashlib.sha1(fallback.encode("utf-8", "replace")).hexdigest()[:16]
    return f"dev_{digest}"


def _monitor_friendly_name(device: str) -> str:
    dd = DISPLAY_DEVICEW()
    dd.cb = ctypes.sizeof(dd)
    if user32.EnumDisplayDevicesW(device, 0, ctypes.byref(dd), 0):
        if dd.DeviceString:
            return dd.DeviceString
    return device


def _monitor_mode(device: str) -> Tuple[int, str]:
    """Frequence de rafraichissement et orientation."""
    dm = DEVMODEW()
    dm.dmSize = ctypes.sizeof(dm)
    if user32.EnumDisplaySettingsW(device, ENUM_CURRENT_SETTINGS, ctypes.byref(dm)):
        # dmDisplayOrientation : 0=0deg, 1=90deg, 2=180deg, 3=270deg
        portrait = dm.dmDisplayOrientation in (1, 3)
        return (
            int(dm.dmDisplayFrequency),
            ORIENTATION_PORTRAIT if portrait else ORIENTATION_LANDSCAPE,
        )
    return (0, ORIENTATION_LANDSCAPE)


def _monitor_dpi(hmonitor: int) -> int:
    dx, dy = ctypes.c_uint(96), ctypes.c_uint(96)
    try:
        ctypes.windll.shcore.GetDpiForMonitor(
            hmonitor, MDT_EFFECTIVE_DPI, ctypes.byref(dx), ctypes.byref(dy)
        )
    except (AttributeError, OSError):
        pass
    return int(dx.value) or 96


def enumerate_monitors() -> List[MonitorInfo]:
    """Liste les moniteurs actuellement connectes.

    Le processus doit etre conscient du DPI (voir
    :func:`wallpaper_studio.system.win_desktop.enable_dpi_awareness`) pour que les
    rectangles correspondent aux pixels physiques.
    """
    found: List[MonitorInfo] = []

    def cb(hmonitor, _hdc, _lprc, _lparam):
        mi = MONITORINFOEXW()
        mi.cbSize = ctypes.sizeof(mi)
        if not user32.GetMonitorInfoW(hmonitor, ctypes.byref(mi)):
            return True
        rm, rw = mi.rcMonitor, mi.rcWork
        device = mi.szDevice
        hz, orientation = _monitor_mode(device)
        index = len(found)
        found.append(
            MonitorInfo(
                key=_monitor_hardware_key(device, device),
                device=device,
                name=_monitor_friendly_name(device),
                rect=(rm.left, rm.top, rm.right - rm.left, rm.bottom - rm.top),
                work_rect=(rw.left, rw.top, rw.right - rw.left, rw.bottom - rw.top),
                is_primary=bool(mi.dwFlags & MONITORINFOF_PRIMARY),
                dpi=_monitor_dpi(hmonitor),
                refresh_hz=hz,
                orientation=orientation,
                index=index,
            )
        )
        return True

    user32.EnumDisplayMonitors(None, None, MONITORENUMPROC(cb), 0)
    # Le moniteur principal en premier, puis de gauche a droite : ordre stable
    # et intuitif pour l'interface.
    found.sort(key=lambda m: (not m.is_primary, m.rect[0], m.rect[1]))
    return [
        MonitorInfo(**{**m.__dict__, "index": i}) for i, m in enumerate(found)
    ]


@dataclass
class MonitorChange:
    """Difference entre deux releves de configuration d'ecrans."""

    added: List[MonitorInfo] = field(default_factory=list)
    removed: List[MonitorInfo] = field(default_factory=list)
    moved: List[MonitorInfo] = field(default_factory=list)

    @property
    def any(self) -> bool:
        return bool(self.added or self.removed or self.moved)

    def describe(self) -> str:
        parts = []
        if self.added:
            parts.append(f"{len(self.added)} ajoute(s)")
        if self.removed:
            parts.append(f"{len(self.removed)} retire(s)")
        if self.moved:
            parts.append(f"{len(self.moved)} redimensionne(s)/deplace(s)")
        return ", ".join(parts) or "aucun changement"


class MonitorManager:
    """Suit la configuration des ecrans et signale les changements.

    Le rafraichissement est explicite (:meth:`refresh`) : l'interface l'appelle
    sur reception de ``WM_DISPLAYCHANGE`` ou du signal Qt equivalent, et le
    moteur l'appelle au reveil de veille.
    """

    def __init__(self) -> None:
        self._monitors: List[MonitorInfo] = []
        self.refresh()

    @property
    def monitors(self) -> List[MonitorInfo]:
        return list(self._monitors)

    @property
    def count(self) -> int:
        return len(self._monitors)

    def by_key(self, key: str) -> Optional[MonitorInfo]:
        return next((m for m in self._monitors if m.key == key), None)

    def primary(self) -> Optional[MonitorInfo]:
        return next((m for m in self._monitors if m.is_primary), None)

    def as_map(self) -> Dict[str, MonitorInfo]:
        return {m.key: m for m in self._monitors}

    def refresh(self) -> MonitorChange:
        """Releve la configuration et retourne les differences."""
        new = enumerate_monitors()
        old_map = {m.key: m for m in self._monitors}
        new_map = {m.key: m for m in new}

        change = MonitorChange(
            added=[m for k, m in new_map.items() if k not in old_map],
            removed=[m for k, m in old_map.items() if k not in new_map],
            moved=[
                m
                for k, m in new_map.items()
                if k in old_map and old_map[k].rect != m.rect
            ],
        )
        self._monitors = new
        if change.any:
            log.info("Configuration d'ecrans modifiee : %s", change.describe())
        return change

    def bounding_rect(self) -> Tuple[int, int, int, int]:
        """Rectangle englobant tous les ecrans : (x, y, largeur, hauteur)."""
        if not self._monitors:
            return (0, 0, 0, 0)
        left = min(m.rect[0] for m in self._monitors)
        top = min(m.rect[1] for m in self._monitors)
        right = max(m.rect[0] + m.rect[2] for m in self._monitors)
        bottom = max(m.rect[1] + m.rect[3] for m in self._monitors)
        return (left, top, right - left, bottom - top)
