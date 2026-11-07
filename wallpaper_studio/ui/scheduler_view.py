"""Planificateur horaire : creation et suivi des regles jour / nuit."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import List, Optional

from PySide6.QtCore import QTime, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from ..data.database import ALL_DAYS_MASK, DAY_NAMES, days_list_from_mask, days_mask_from_list
from ..data.models import ScheduleRule
from ..media.types import FillMode
from ..scheduler.rules import ConflictPolicy, validate_rule
from .theme import icon
from .widgets.common import Badge, hint_label

log = logging.getLogger(__name__)


class RuleDialog(QDialog):
    """Boite de dialogue de creation ou de modification d'une regle."""

    def __init__(self, repos, engine, rule: Optional[ScheduleRule] = None, parent=None):
        super().__init__(parent)
        self._repos = repos
        self._engine = engine
        self._rule = rule
        self.setWindowTitle("Modifier la regle" if rule else "Nouvelle regle horaire")
        self.setMinimumWidth(460)
        self._build()
        if rule:
            self._load(rule)

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(10)

        self._name = QLineEdit()
        self._name.setPlaceholderText("Par exemple : Fond de nuit")
        form.addRow("Nom :", self._name)

        self._media = QComboBox()
        for item in self._repos.media.list(order_by="title", descending=False):
            suffix = "  (fichier manquant)" if item.missing else ""
            self._media.addItem(f"{item.title}{suffix}", item.id)
        form.addRow("Fond d'ecran :", self._media)

        self._monitor = QComboBox()
        self._monitor.addItem("Tous les ecrans", None)
        for monitor in self._engine.monitor_manager.monitors:
            self._monitor.addItem(f"{monitor.label} - {monitor.name}", monitor.key)
        form.addRow("Ecran :", self._monitor)

        times = QHBoxLayout()
        self._start = QTimeEdit(QTime(8, 0))
        self._start.setDisplayFormat("HH:mm")
        self._end = QTimeEdit(QTime(22, 0))
        self._end.setDisplayFormat("HH:mm")
        self._start.timeChanged.connect(self._update_hint)
        self._end.timeChanged.connect(self._update_hint)
        times.addWidget(self._start)
        times.addWidget(QLabel("jusqu'a"))
        times.addWidget(self._end)
        times.addStretch(1)
        form.addRow("Plage horaire :", times)

        days = QHBoxLayout()
        self._days = []
        for index, name in enumerate(DAY_NAMES):
            box = QCheckBox(name[:3])
            box.setChecked(True)
            box.toggled.connect(self._update_hint)
            self._days.append(box)
            days.addWidget(box)
        days.addStretch(1)
        form.addRow("Jours :", days)

        quick = QHBoxLayout()
        for label, mask in (
            ("Tous", ALL_DAYS_MASK),
            ("Lun-Ven", days_mask_from_list([0, 1, 2, 3, 4])),
            ("Week-end", days_mask_from_list([5, 6])),
        ):
            button = QPushButton(label)
            button.setObjectName("ghost")
            button.clicked.connect(lambda _=False, m=mask: self._set_days(m))
            quick.addWidget(button)
        quick.addStretch(1)
        form.addRow("", quick)

        self._priority = QSpinBox()
        self._priority.setRange(0, 100)
        self._priority.setToolTip(
            "En cas de chevauchement, la regle de priorite la plus elevee gagne."
        )
        form.addRow("Priorite :", self._priority)

        self._fill = QComboBox()
        self._fill.addItem("Utiliser le reglage de l'ecran", None)
        for mode in FillMode:
            self._fill.addItem(mode.label, mode.value)
        form.addRow("Cadrage :", self._fill)

        self._enabled = QCheckBox("Regle active")
        self._enabled.setChecked(True)
        form.addRow("", self._enabled)

        layout.addLayout(form)

        self._hint = hint_label("")
        layout.addWidget(self._hint)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Enregistrer")
        buttons.button(QDialogButtonBox.Cancel).setText("Annuler")
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._update_hint()

    def _set_days(self, mask: int) -> None:
        for index, box in enumerate(self._days):
            box.setChecked(bool(mask & (1 << index)))

    def _update_hint(self) -> None:
        start = self._start.time()
        end = self._end.time()
        start_min = start.hour() * 60 + start.minute()
        end_min = end.hour() * 60 + end.minute()
        if end_min <= start_min:
            duration = (1440 - start_min) + end_min
            self._hint.setText(
                f"Cette plage traverse minuit : de {start.toString('HH:mm')} "
                f"le jour coche jusqu'a {end.toString('HH:mm')} le lendemain "
                f"({duration // 60} h {duration % 60:02d})."
            )
        else:
            duration = end_min - start_min
            self._hint.setText(
                f"Duree de la plage : {duration // 60} h {duration % 60:02d}."
            )

    def _load(self, rule: ScheduleRule) -> None:
        self._name.setText(rule.name)
        index = self._media.findData(rule.media_id)
        self._media.setCurrentIndex(max(0, index))
        index = self._monitor.findData(rule.monitor_key)
        self._monitor.setCurrentIndex(max(0, index))
        self._start.setTime(QTime(rule.start_minute // 60, rule.start_minute % 60))
        self._end.setTime(QTime(rule.end_minute // 60, rule.end_minute % 60))
        self._set_days(rule.days_mask)
        self._priority.setValue(rule.priority)
        index = self._fill.findData(rule.fill_mode.value if rule.fill_mode else None)
        self._fill.setCurrentIndex(max(0, index))
        self._enabled.setChecked(rule.enabled)

    def rule(self) -> ScheduleRule:
        start = self._start.time()
        end = self._end.time()
        fill = self._fill.currentData()
        return ScheduleRule(
            id=self._rule.id if self._rule else None,
            name=self._name.text().strip(),
            monitor_key=self._monitor.currentData(),
            media_id=self._media.currentData() or 0,
            start_minute=start.hour() * 60 + start.minute(),
            end_minute=end.hour() * 60 + end.minute(),
            days_mask=days_mask_from_list(
                [i for i, b in enumerate(self._days) if b.isChecked()]
            ),
            priority=self._priority.value(),
            enabled=self._enabled.isChecked(),
            fill_mode=FillMode(fill) if fill else None,
        )

    def _accept(self) -> None:
        problems = validate_rule(self.rule())
        if problems:
            QMessageBox.warning(self, "Regle incomplete", "\n".join(problems))
            return
        self.accept()


class SchedulerView(QWidget):
    """Page Horaires."""

    notify = Signal(str, str)
    rules_changed = Signal()

    def __init__(self, repos, engine, scheduler, settings, parent=None):
        super().__init__(parent)
        self._repos = repos
        self._engine = engine
        self._scheduler = scheduler
        self._settings = settings
        self._build()

        # Rafraichit le compte a rebours sans solliciter la base.
        # Le compte a rebours s'exprime en minutes : inutile de le recalculer
        # chaque seconde.
        self._tick = QTimer(self)
        self._tick.setInterval(5000)
        self._tick.timeout.connect(self._on_tick)
        self._tick.start()
        self.refresh()

    def set_updates_active(self, active: bool) -> None:
        if active and not self._tick.isActive():
            self._tick.start()
            self._update_status()
        elif not active and self._tick.isActive():
            self._tick.stop()

    def _on_tick(self) -> None:
        if self.isVisible():
            self._update_status()

    # --- Construction ------------------------------------------------------
    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(14)

        header = QHBoxLayout()
        title = QLabel("Horaires")
        title.setObjectName("pageTitle")
        header.addWidget(title)
        header.addStretch(1)

        self._active = QCheckBox("Planification automatique")
        self._active.setChecked(self._settings.get("planification_active", True))
        self._active.toggled.connect(self._toggle_scheduler)
        header.addWidget(self._active)

        self._btn_suspend = QPushButton("Suspendre 1 h")
        self._btn_suspend.clicked.connect(self._suspend_one_hour)
        header.addWidget(self._btn_suspend)

        add = QPushButton("  Nouvelle regle")
        add.setObjectName("primary")
        add.setIcon(icon("ajouter"))
        add.clicked.connect(self.create_rule)
        header.addWidget(add)
        root.addLayout(header)

        # --- Bandeau d'etat ---
        status_row = QHBoxLayout()
        self._status = Badge("", "neutre")
        status_row.addWidget(self._status)
        self._next = QLabel("")
        self._next.setObjectName("hint")
        status_row.addWidget(self._next)
        status_row.addStretch(1)

        status_row.addWidget(QLabel("En cas de conflit :"))
        self._policy = QComboBox()
        for policy in ConflictPolicy:
            self._policy.addItem(policy.label, policy.value)
        current = self._settings.get("politique_conflit", "priority")
        self._policy.setCurrentIndex(max(0, self._policy.findData(current)))
        self._policy.currentIndexChanged.connect(self._change_policy)
        status_row.addWidget(self._policy)
        root.addLayout(status_row)

        root.addWidget(
            hint_label(
                "Une plage dont l'heure de fin precede l'heure de debut traverse minuit : "
                "22h00 - 08h00 couvre donc toute la nuit. Les jours coches designent le "
                "jour ou la plage commence."
            )
        )

        # --- Tableau des regles ---
        self._table = QTableWidget(0, 8)
        self._table.setHorizontalHeaderLabels(
            ["Actif", "Nom", "Fond d'ecran", "Ecran", "Plage", "Jours", "Priorite", ""]
        )
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.setAlternatingRowColors(False)
        head = self._table.horizontalHeader()
        head.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        head.setSectionResizeMode(1, QHeaderView.Stretch)
        head.setSectionResizeMode(2, QHeaderView.Stretch)
        head.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        head.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        head.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        head.setSectionResizeMode(6, QHeaderView.ResizeToContents)
        head.setSectionResizeMode(7, QHeaderView.ResizeToContents)
        self._table.doubleClicked.connect(lambda: self.edit_rule())
        root.addWidget(self._table, 1)

        # --- Actions ---
        actions = QHBoxLayout()
        for label, slot in (
            ("Modifier", self.edit_rule),
            ("Dupliquer", self._duplicate_rule),
            ("Supprimer", self._delete_rule),
        ):
            button = QPushButton(label)
            button.clicked.connect(slot)
            actions.addWidget(button)
        actions.addStretch(1)

        preset = QPushButton("  Creer un programme jour / nuit")
        preset.setIcon(icon("horaires"))
        preset.clicked.connect(self._create_day_night_preset)
        actions.addWidget(preset)
        root.addLayout(actions)

    # --- Donnees -----------------------------------------------------------
    def refresh(self) -> None:
        rules = self._repos.schedule.list()
        monitors = {m.key: m for m in self._engine.monitor_manager.monitors}

        self._table.setRowCount(len(rules))
        for row, rule in enumerate(rules):
            active = QCheckBox()
            active.setChecked(rule.enabled)
            active.toggled.connect(
                lambda checked, rid=rule.id: self._set_enabled(rid, checked)
            )
            holder = QWidget()
            holder_layout = QHBoxLayout(holder)
            holder_layout.setContentsMargins(10, 0, 0, 0)
            holder_layout.addWidget(active)
            self._table.setCellWidget(row, 0, holder)

            if rule.monitor_key is None:
                screen = "Tous"
            else:
                monitor = monitors.get(rule.monitor_key)
                screen = monitor.label if monitor else "Ecran absent"

            values = [
                rule.name,
                rule.media_title or "(fond supprime)",
                screen,
                rule.range_text,
                rule.days_text,
                str(rule.priority),
            ]
            for column, value in enumerate(values, start=1):
                cell = QTableWidgetItem(value)
                cell.setData(Qt.UserRole, rule.id)
                if not rule.enabled:
                    cell.setForeground(Qt.gray)
                self._table.setItem(row, column, cell)

            state = QTableWidgetItem("en cours" if self._is_active_now(rule) else "")
            state.setData(Qt.UserRole, rule.id)
            self._table.setItem(row, 7, state)

        self._update_status()

    def _is_active_now(self, rule: ScheduleRule) -> bool:
        from ..scheduler.rules import rule_is_active

        return rule_is_active(rule, datetime.now())

    def _selected_rule_id(self) -> Optional[int]:
        row = self._table.currentRow()
        if row < 0:
            return None
        item = self._table.item(row, 1)
        return item.data(Qt.UserRole) if item else None

    def _update_status(self) -> None:
        if not self._scheduler.enabled:
            self._status.setText("Planification desactivee")
            self._status.set_kind("alerte")
        elif self._scheduler.is_suspended:
            self._status.setText("Suspendue")
            self._status.set_kind("alerte")
        else:
            count = self._repos.schedule.count(enabled_only=True)
            self._status.setText(f"{count} regle(s) active(s)")
            self._status.set_kind("succes" if count else "neutre")

        self._next.setText(self._scheduler.describe_next())

    # --- Actions -----------------------------------------------------------
    def create_rule(self, media_id: Optional[int] = None) -> None:
        if self._repos.media.count() == 0:
            self.notify.emit(
                "Importez d'abord des fonds dans la bibliotheque.", "alerte"
            )
            return
        dialog = RuleDialog(self._repos, self._engine, parent=self)
        if media_id:
            index = dialog._media.findData(media_id)
            if index >= 0:
                dialog._media.setCurrentIndex(index)
        if dialog.exec() == QDialog.Accepted:
            self._repos.schedule.add(dialog.rule())
            self._after_change("Regle creee.")

    def edit_rule(self) -> None:
        rule_id = self._selected_rule_id()
        if rule_id is None:
            self.notify.emit("Selectionnez une regle a modifier.", "info")
            return
        rule = self._repos.schedule.get(rule_id)
        if rule is None:
            return
        dialog = RuleDialog(self._repos, self._engine, rule, parent=self)
        if dialog.exec() == QDialog.Accepted:
            self._repos.schedule.update(dialog.rule())
            self._after_change("Regle mise a jour.")

    def _duplicate_rule(self) -> None:
        rule_id = self._selected_rule_id()
        if rule_id is None:
            return
        rule = self._repos.schedule.get(rule_id)
        if rule is None:
            return
        rule.id = None
        rule.name = f"{rule.name} (copie)"
        self._repos.schedule.add(rule)
        self._after_change("Regle dupliquee.")

    def _delete_rule(self) -> None:
        rule_id = self._selected_rule_id()
        if rule_id is None:
            return
        rule = self._repos.schedule.get(rule_id)
        answer = QMessageBox.question(
            self, "Supprimer la regle",
            f"Supprimer la regle « {rule.name if rule else ''} » ?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if answer == QMessageBox.Yes:
            self._repos.schedule.delete(rule_id)
            self._after_change("Regle supprimee.")

    def _set_enabled(self, rule_id: int, enabled: bool) -> None:
        self._repos.schedule.set_enabled(rule_id, enabled)
        self._scheduler.forget_applied()
        self._scheduler.request_evaluation()
        self.refresh()

    def _after_change(self, message: str) -> None:
        self._scheduler.forget_applied()
        self._scheduler.request_evaluation()
        self.refresh()
        self.rules_changed.emit()
        self.notify.emit(message, "succes")

    def _toggle_scheduler(self, enabled: bool) -> None:
        self._settings.set("planification_active", enabled)
        self._scheduler.set_enabled(enabled)
        self._update_status()
        self.notify.emit(
            "Planification activee." if enabled else "Planification desactivee.",
            "succes" if enabled else "info",
        )

    def _suspend_one_hour(self) -> None:
        from datetime import timedelta

        if self._scheduler.is_suspended:
            self._scheduler.suspend_until(None)
            self._btn_suspend.setText("Suspendre 1 h")
            self.notify.emit("Planification reprise.", "succes")
        else:
            self._scheduler.suspend_until(datetime.now() + timedelta(hours=1))
            self._btn_suspend.setText("Reprendre")
            self.notify.emit("Planification suspendue pendant 1 heure.", "info")
        self._update_status()

    def _change_policy(self) -> None:
        value = self._policy.currentData()
        self._settings.set("politique_conflit", value)
        self._scheduler.policy = ConflictPolicy(value)
        self.notify.emit("Politique de conflit mise a jour.", "succes")

    def _create_day_night_preset(self) -> None:
        """Assistant : cree en deux clics un programme jour / nuit complet."""
        items = self._repos.media.list(order_by="title", descending=False)
        if len(items) < 2:
            self.notify.emit(
                "Importez au moins deux fonds pour creer un programme jour / nuit.",
                "alerte",
            )
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("Programme jour / nuit")
        layout = QVBoxLayout(dialog)
        form = QFormLayout()

        day = QComboBox()
        night = QComboBox()
        for item in items:
            day.addItem(item.title, item.id)
            night.addItem(item.title, item.id)
        night.setCurrentIndex(min(1, len(items) - 1))

        start = QTimeEdit(QTime(8, 0))
        start.setDisplayFormat("HH:mm")
        end = QTimeEdit(QTime(22, 0))
        end.setDisplayFormat("HH:mm")

        monitor = QComboBox()
        monitor.addItem("Tous les ecrans", None)
        for m in self._engine.monitor_manager.monitors:
            monitor.addItem(f"{m.label} - {m.name}", m.key)

        form.addRow("Fond de jour :", day)
        form.addRow("Fond de nuit :", night)
        form.addRow("Le jour commence a :", start)
        form.addRow("La nuit commence a :", end)
        form.addRow("Ecran :", monitor)
        layout.addLayout(form)
        layout.addWidget(
            hint_label(
                "Deux regles complementaires seront creees : elles se relaient "
                "sans trou ni recouvrement, la regle de nuit traversant minuit."
            )
        )

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Creer les deux regles")
        buttons.button(QDialogButtonBox.Cancel).setText("Annuler")
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        if dialog.exec() != QDialog.Accepted:
            return

        day_min = start.time().hour() * 60 + start.time().minute()
        night_min = end.time().hour() * 60 + end.time().minute()
        key = monitor.currentData()

        self._repos.schedule.add(
            ScheduleRule(
                name="Fond de jour", monitor_key=key, media_id=day.currentData(),
                start_minute=day_min, end_minute=night_min,
            )
        )
        self._repos.schedule.add(
            ScheduleRule(
                name="Fond de nuit", monitor_key=key, media_id=night.currentData(),
                start_minute=night_min, end_minute=day_min,
            )
        )
        self._after_change("Programme jour / nuit cree.")
