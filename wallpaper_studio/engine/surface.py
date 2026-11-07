"""Fenetre de fond d'ecran : une par moniteur.

Une surface est une fenetre Qt sans bordure, reparentee dans la couche
``WorkerW`` de l'Explorateur (voir :mod:`wallpaper_studio.system.win_desktop`). Elle
contient le widget fourni par un moteur de rendu, plus une eventuelle couche
d'effets superposee.

Point d'attention : la fenetre est creee *de premier niveau* puis reparentee.
Qt a besoin d'une fenetre native (``winId()`` la force) et doit avoir realise la
fenetre avant que ``SetParent`` soit appele, d'ou l'ordre dans :meth:`attach`.
"""

from __future__ import annotations

import logging
from typing import Optional, Tuple

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QStackedLayout, QWidget

from ..system import win_desktop as wd
from ..system.monitors import MonitorInfo

log = logging.getLogger(__name__)


class WallpaperSurface(QWidget):
    """Fenetre hote d'un fond d'ecran pour un moniteur donne."""

    #: Emis lorsque la surface a perdu son support (redemarrage d'explorer.exe).
    detached = Signal(str)

    def __init__(self, monitor: MonitorInfo, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._monitor = monitor
        self._host: Optional[wd.WallpaperHost] = None
        self._content: Optional[QWidget] = None
        self._overlay: Optional[QWidget] = None
        self._attached = False

        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.Tool                     # hors barre des taches et hors Alt+Tab
            | Qt.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_OpaquePaintEvent, True)
        self.setAttribute(Qt.WA_NativeWindow, True)
        self.setObjectName(f"surface_{monitor.key}")

        # QStackedLayout en mode StackAll empile le contenu et la couche
        # d'effets, tous deux visibles simultanement.
        self._layout = QStackedLayout(self)
        self._layout.setStackingMode(QStackedLayout.StackAll)
        self._layout.setContentsMargins(0, 0, 0, 0)

        self.setGeometry(*self._geometry_tuple())

    # --- Informations ------------------------------------------------------
    @property
    def monitor(self) -> MonitorInfo:
        return self._monitor

    @property
    def monitor_key(self) -> str:
        return self._monitor.key

    @property
    def is_attached(self) -> bool:
        return self._attached and wd.host_is_alive(self._host)

    def _geometry_tuple(self) -> Tuple[int, int, int, int]:
        x, y, w, h = self._monitor.rect
        return (x, y, w, h)

    def hwnd(self) -> int:
        return int(self.winId())

    # --- Rattachement au bureau -------------------------------------------
    def attach(self, host: wd.WallpaperHost) -> bool:
        """Reparente la surface dans la couche de fond d'ecran."""
        self._host = host

        # Forcer la creation de la fenetre native avant SetParent.
        self.show()
        hwnd = self.hwnd()

        ok = wd.attach_to_host(hwnd, host, self._geometry_tuple())
        self._attached = ok
        if ok:
            log.info(
                "Surface %s rattachee (hwnd=%s, %s)",
                self._monitor.label, hwnd, host.layout,
            )
        else:
            log.error("Echec du rattachement de la surface %s", self._monitor.label)
        return ok

    def reattach(self, host: wd.WallpaperHost) -> bool:
        """Rattache apres un redemarrage de l'Explorateur."""
        self._attached = False
        return self.attach(host)

    def detach(self) -> None:
        if self._attached:
            wd.detach_from_host(self.hwnd())
            self._attached = False

    def update_monitor(self, monitor: MonitorInfo) -> None:
        """Suit un changement de resolution ou de position du moniteur."""
        self._monitor = monitor
        rect = self._geometry_tuple()
        self.setGeometry(*rect)
        if self._attached and self._host:
            wd.move_in_host(self.hwnd(), self._host, rect)
        log.info("Surface %s repositionnee : %s", monitor.label, rect)

    # --- Contenu -----------------------------------------------------------
    def set_content(self, widget: Optional[QWidget]) -> None:
        """Remplace le widget de rendu. L'ancien est retire mais pas detruit.

        La destruction appartient au moteur de rendu, qui doit d'abord liberer
        ses propres ressources (lecteur video, par exemple).
        """
        if self._content is not None:
            self._layout.removeWidget(self._content)
            self._content.setParent(None)
        self._content = widget
        if widget is not None:
            self._layout.addWidget(widget)
            # Le contenu doit rester sous la couche d'effets.
            if self._overlay is not None:
                self._layout.removeWidget(self._overlay)
                self._layout.addWidget(self._overlay)
                self._overlay.raise_()
            widget.show()

    def set_overlay(self, widget: Optional[QWidget]) -> None:
        """Installe (ou retire) la couche d'effets superposee."""
        if self._overlay is not None:
            self._layout.removeWidget(self._overlay)
            self._overlay.setParent(None)
        self._overlay = widget
        if widget is not None:
            self._layout.addWidget(widget)
            widget.raise_()
            widget.show()

    def content(self) -> Optional[QWidget]:
        return self._content

    # --- Rendu -------------------------------------------------------------
    def paintEvent(self, event) -> None:  # noqa: N802 - API Qt
        # Fond noir : evite qu'un contenu en mode « Ajuster » laisse voir des
        # artefacts du bureau dans les bandes laterales.
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0))

    def closeEvent(self, event) -> None:  # noqa: N802 - API Qt
        self.detach()
        super().closeEvent(event)
