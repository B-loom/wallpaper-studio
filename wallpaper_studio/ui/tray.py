"""Icone et menu dans la zone de notification Windows.

L'application reste active tant que l'icone est presente : fermer la fenetre
principale n'arrete donc pas le planificateur.
"""

from __future__ import annotations

import logging
from typing import Optional

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from .. import APP_NAME
from .theme import app_icon

log = logging.getLogger(__name__)


class TrayIcon(QObject):
    """Icone de notification et son menu contextuel."""

    show_window = Signal()
    toggle_pause = Signal()
    toggle_scheduler = Signal()
    next_wallpaper = Signal()
    quit_requested = Signal()

    def __init__(self, controller, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._controller = controller
        self._tray = QSystemTrayIcon(app_icon(64), self)
        self._tray.setToolTip(APP_NAME)
        self._build_menu()
        self._tray.activated.connect(self._on_activated)

    def _build_menu(self) -> None:
        menu = QMenu()

        open_action = QAction("Ouvrir Wallpaper Studio", menu)
        open_action.triggered.connect(self.show_window.emit)
        menu.addAction(open_action)
        menu.addSeparator()

        self._pause_action = QAction("Mettre les fonds en pause", menu)
        self._pause_action.triggered.connect(self.toggle_pause.emit)
        menu.addAction(self._pause_action)

        self._scheduler_action = QAction("Suspendre la planification", menu)
        self._scheduler_action.triggered.connect(self.toggle_scheduler.emit)
        menu.addAction(self._scheduler_action)
        menu.addSeparator()

        self._status_action = QAction("", menu)
        self._status_action.setEnabled(False)
        menu.addAction(self._status_action)
        menu.addSeparator()

        quit_action = QAction("Quitter completement", menu)
        quit_action.triggered.connect(self.quit_requested.emit)
        menu.addAction(quit_action)

        self._menu = menu
        self._tray.setContextMenu(menu)
        menu.aboutToShow.connect(self.refresh)

    def show(self) -> None:
        self._tray.show()
        self.refresh()

    def hide(self) -> None:
        self._tray.hide()

    @property
    def is_available(self) -> bool:
        return QSystemTrayIcon.isSystemTrayAvailable()

    def refresh(self) -> None:
        """Met le menu a jour selon l'etat courant."""
        engine = self._controller.engine
        scheduler = self._controller.scheduler

        self._pause_action.setText(
            "Reprendre la lecture" if engine.is_paused
            else "Mettre les fonds en pause"
        )
        self._scheduler_action.setText(
            "Reactiver la planification" if not scheduler.enabled
            else "Suspendre la planification"
        )
        self._status_action.setText(scheduler.describe_next())
        self._tray.setToolTip(
            f"{APP_NAME}\n"
            f"{engine.active_count} fond(s) actif(s)\n"
            f"{scheduler.describe_next()}"
        )

    def notify(self, message: str, kind: str = "info") -> None:
        """Notification systeme, si l'utilisateur les a laissees actives."""
        if not self._controller.settings.get("notifications", True):
            return
        icons = {
            "erreur": QSystemTrayIcon.Critical,
            "alerte": QSystemTrayIcon.Warning,
        }
        self._tray.showMessage(
            APP_NAME, message, icons.get(kind, QSystemTrayIcon.Information), 4000
        )

    def _on_activated(self, reason) -> None:
        if reason in (QSystemTrayIcon.DoubleClick, QSystemTrayIcon.Trigger):
            self.show_window.emit()
