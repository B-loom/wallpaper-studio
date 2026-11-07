"""Suivi global de la position du curseur.

Les fenetres reparentees dans ``WorkerW`` ne recoivent pas les evenements souris
du bureau : Windows les envoie a ``SHELLDLL_DefView``, qui est au-dessus. Pour
rendre les fonds interactifs, on interroge donc periodiquement la position du
curseur avec ``GetCursorPos``.

Le cout est negligeable (un appel systeme par cycle) et le suivi s'arrete de
lui-meme quand aucun fond interactif n'est actif.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wintypes
import logging
from typing import Optional, Tuple

from PySide6.QtCore import QObject, QTimer, Signal

log = logging.getLogger(__name__)

user32 = ctypes.WinDLL("user32", use_last_error=True)


def cursor_position() -> Optional[Tuple[int, int]]:
    """Position du curseur en coordonnees ecran, ou ``None`` en cas d'echec."""
    point = wintypes.POINT()
    if user32.GetCursorPos(ctypes.byref(point)):
        return (point.x, point.y)
    return None


class MouseTracker(QObject):
    """Emet la position du curseur a intervalle regulier quand elle change."""

    moved = Signal(int, int)

    def __init__(self, interval_ms: int = 60, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._last: Optional[Tuple[int, int]] = None
        self._timer = QTimer(self)
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(self._poll)

    @property
    def is_running(self) -> bool:
        return self._timer.isActive()

    def start(self) -> None:
        if not self._timer.isActive():
            self._timer.start()
            log.debug("Suivi du curseur demarre")

    def stop(self) -> None:
        if self._timer.isActive():
            self._timer.stop()
            self._last = None
            log.debug("Suivi du curseur arrete")

    def set_interval(self, interval_ms: int) -> None:
        self._timer.setInterval(max(16, interval_ms))

    def _poll(self) -> None:
        position = cursor_position()
        if position is None or position == self._last:
            return
        self._last = position
        self.moved.emit(position[0], position[1])
