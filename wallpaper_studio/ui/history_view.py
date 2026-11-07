"""Historique des fonds d'ecran appliques."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .widgets.common import hint_label


class HistoryView(QWidget):
    """Page Historique."""

    reapply_requested = Signal(int)   # media_id
    notify = Signal(str, str)

    def __init__(self, repos, engine, parent=None):
        super().__init__(parent)
        self._repos = repos
        self._engine = engine
        self._build()
        self.refresh()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(14)

        header = QHBoxLayout()
        title = QLabel("Historique")
        title.setObjectName("pageTitle")
        header.addWidget(title)
        header.addStretch(1)

        self._filter = QComboBox()
        self._filter.currentIndexChanged.connect(self.refresh)
        header.addWidget(self._filter)

        refresh = QPushButton("Actualiser")
        refresh.clicked.connect(self.refresh)
        header.addWidget(refresh)

        clear = QPushButton("Vider l'historique")
        clear.setObjectName("ghost")
        clear.clicked.connect(self._clear)
        header.addWidget(clear)
        root.addLayout(header)

        root.addWidget(
            hint_label(
                "Chaque changement de fond est enregistre, qu'il vienne du "
                "planificateur ou d'une action manuelle. Double-cliquez sur une "
                "ligne pour reappliquer ce fond."
            )
        )

        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(
            ["Date et heure", "Ecran", "Fond d'ecran", "Origine", "Regle"]
        )
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        head = self._table.horizontalHeader()
        head.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        head.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        head.setSectionResizeMode(2, QHeaderView.Stretch)
        head.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        head.setSectionResizeMode(4, QHeaderView.Stretch)
        self._table.doubleClicked.connect(self._reapply)
        root.addWidget(self._table, 1)

        self._status = QLabel()
        self._status.setObjectName("hint")
        root.addWidget(self._status)

    def refresh(self) -> None:
        monitors = {m.key: m for m in self._engine.monitor_manager.monitors}

        previous = self._filter.currentData()
        self._filter.blockSignals(True)
        self._filter.clear()
        self._filter.addItem("Tous les ecrans", None)
        for monitor in monitors.values():
            self._filter.addItem(monitor.label, monitor.key)
        index = self._filter.findData(previous)
        self._filter.setCurrentIndex(max(0, index))
        self._filter.blockSignals(False)

        entries = self._repos.history.list(
            limit=500, monitor_key=self._filter.currentData()
        )
        self._table.setRowCount(len(entries))
        for row, entry in enumerate(entries):
            monitor = monitors.get(entry.monitor_key)
            values = [
                entry.time_text,
                monitor.label if monitor else "Ecran absent",
                entry.media_title or "(fond supprime)",
                "Planificateur" if entry.reason == "planificateur" else "Manuel",
                entry.rule_name or "-",
            ]
            for column, value in enumerate(values):
                cell = QTableWidgetItem(value)
                cell.setData(Qt.UserRole, entry.media_id)
                self._table.setItem(row, column, cell)

        self._status.setText(f"{len(entries)} evenement(s) affiche(s)")

    def _reapply(self) -> None:
        row = self._table.currentRow()
        if row < 0:
            return
        item = self._table.item(row, 2)
        media_id = item.data(Qt.UserRole) if item else None
        if media_id is None:
            self.notify.emit("Ce fond n'existe plus dans la bibliotheque.", "alerte")
            return
        self.reapply_requested.emit(media_id)

    def _clear(self) -> None:
        answer = QMessageBox.question(
            self, "Vider l'historique",
            "Effacer tout l'historique des changements de fond ?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if answer == QMessageBox.Yes:
            self._repos.history.clear()
            self.refresh()
            self.notify.emit("Historique efface.", "succes")
