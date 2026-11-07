"""Observation de la fenetre de premier plan : jeux et fenetres maximisees.

Sert a suspendre les fonds d'ecran animes quand ils ne sont de toute facon pas
visibles, ce qui libere processeur et batterie.

Limite assumee : Windows n'expose pas d'API fiable pour dire « ceci est un jeu ».
On se fonde sur un faisceau d'indices observables : la fenetre de premier plan
couvre tout un moniteur, n'a pas de bordure, et n'appartient ni au bureau ni au
shell. C'est le meme critere que celui utilise par la detection de mode « plein
ecran exclusif » de Windows pour desactiver les notifications.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wintypes
import logging
from dataclasses import dataclass
from typing import Optional, Tuple

log = logging.getLogger(__name__)

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

GWL_STYLE = -16
GWL_EXSTYLE = -20
WS_CAPTION = 0x00C00000
WS_THICKFRAME = 0x00040000
WS_MAXIMIZE = 0x01000000
WS_EX_TOOLWINDOW = 0x00000080

SW_SHOWMAXIMIZED = 3

#: Classes appartenant au bureau ou au shell : leur presence au premier plan ne
#: doit jamais declencher une mise en pause.
_SHELL_CLASSES = {
    "Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd",
    "Windows.UI.Core.CoreWindow", "ForegroundStaging", "MultitaskingViewFrame",
    "XamlExplorerHostIslandWindow",
}

if ctypes.sizeof(ctypes.c_void_p) == 8:
    _GetWindowLong = user32.GetWindowLongPtrW
else:  # pragma: no cover
    _GetWindowLong = user32.GetWindowLongW
_GetWindowLong.argtypes = [wintypes.HWND, ctypes.c_int]
_GetWindowLong.restype = ctypes.c_ssize_t


class WINDOWPLACEMENT(ctypes.Structure):
    _fields_ = [
        ("length", wintypes.UINT), ("flags", wintypes.UINT),
        ("showCmd", wintypes.UINT), ("ptMinPosition", wintypes.POINT),
        ("ptMaxPosition", wintypes.POINT), ("rcNormalPosition", wintypes.RECT),
    ]


@dataclass(frozen=True)
class ForegroundInfo:
    """Etat de la fenetre de premier plan."""

    hwnd: int
    title: str
    class_name: str
    process_name: str
    rect: Tuple[int, int, int, int]
    is_fullscreen: bool
    is_maximized: bool
    is_shell: bool

    @property
    def should_pause_fullscreen(self) -> bool:
        return self.is_fullscreen and not self.is_shell

    @property
    def should_pause_maximized(self) -> bool:
        return (self.is_maximized or self.is_fullscreen) and not self.is_shell


def _window_text(hwnd: int) -> str:
    length = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    return buf.value


def _window_class(hwnd: int) -> str:
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, 256)
    return buf.value


def _process_name(hwnd: int) -> str:
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if not pid.value:
        return ""
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
    if not handle:
        return ""
    try:
        size = wintypes.DWORD(260)
        buf = ctypes.create_unicode_buffer(size.value)
        if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            from pathlib import PurePath

            return PurePath(buf.value).name
    finally:
        kernel32.CloseHandle(handle)
    return ""


def _monitor_rect_for(hwnd: int) -> Optional[Tuple[int, int, int, int]]:
    """Rectangle du moniteur portant la fenetre."""
    MONITOR_DEFAULTTONEAREST = 2

    class MONITORINFO(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
            ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD),
        ]

    hmon = user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST)
    if not hmon:
        return None
    mi = MONITORINFO()
    mi.cbSize = ctypes.sizeof(mi)
    if not user32.GetMonitorInfoW(hmon, ctypes.byref(mi)):
        return None
    r = mi.rcMonitor
    return (r.left, r.top, r.right, r.bottom)


def foreground_info() -> Optional[ForegroundInfo]:
    """Decrit la fenetre de premier plan, ou ``None`` s'il n'y en a pas."""
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return None

    cls = _window_class(hwnd)
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    window = (rect.left, rect.top, rect.right, rect.bottom)

    monitor = _monitor_rect_for(hwnd)
    style = _GetWindowLong(hwnd, GWL_STYLE)
    has_frame = bool(style & (WS_CAPTION | WS_THICKFRAME))

    # Plein ecran : couvre exactement le moniteur et n'a pas de cadre.
    is_fullscreen = False
    if monitor is not None:
        covers = (
            window[0] <= monitor[0] and window[1] <= monitor[1]
            and window[2] >= monitor[2] and window[3] >= monitor[3]
        )
        is_fullscreen = covers and not has_frame

    placement = WINDOWPLACEMENT()
    placement.length = ctypes.sizeof(placement)
    user32.GetWindowPlacement(hwnd, ctypes.byref(placement))
    is_maximized = placement.showCmd == SW_SHOWMAXIMIZED

    return ForegroundInfo(
        hwnd=hwnd,
        title=_window_text(hwnd),
        class_name=cls,
        process_name=_process_name(hwnd),
        rect=window,
        is_fullscreen=is_fullscreen,
        is_maximized=is_maximized,
        is_shell=cls in _SHELL_CLASSES,
    )


def is_fullscreen_app_active() -> bool:
    """Vrai si une application occupe tout un ecran sans bordure (jeu, video)."""
    info = foreground_info()
    return bool(info and info.should_pause_fullscreen)
