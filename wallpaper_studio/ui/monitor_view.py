"""Gestion multi-ecrans : schema, reglages par ecran et modes d'affichage."""

from __future__ import annotations

import logging
from typing import Dict, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from ..data.models import MonitorConfig
from ..media.types import FillMode
from .theme import icon
from .widgets.common import Badge, MonitorDiagram, hint_label

log = logging.getLogger(__name__)

MODE_INDEPENDANT = "independant"
MODE_IDENTIQUE = "identique"
MODE_PANORAMIQUE = "panoramique"


class MonitorView(QWidget):
    """Page Ecrans."""

    apply_to_monitor = Signal(str)        # cle ecran : applique la selection
    clear_monitor = Signal(str)
    restore_previous = Signal(str)
    pause_monitor = Signal(str, bool)
    settings_changed = Signal(str)        # cle ecran
    span_requested = Signal()
    same_on_all_requested = Signal()
    notify = Signal(str, str)

    def __init__(self, engine, repos, settings, parent=None):
        super().__init__(parent)
        self._engine = engine
        self._repos = repos
        self._settings = settings
        self._selected: Optional[str] = None
        self._loading = False
        self._build()
        self.refresh()

    # --- Construction ------------------------------------------------------
    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(14)

        header = QHBoxLayout()
        title = QLabel("Ecrans")
        title.setObjectName("pageTitle")
        header.addWidget(title)
        header.addStretch(1)

        self._count_badge = Badge("", "neutre")
        header.addWidget(self._count_badge)

        refresh = QPushButton("  Redetecter")
        refresh.setIcon(icon("ecrans"))
        refresh.clicked.connect(self._redetect)
        header.addWidget(refresh)
        root.addLayout(header)

        root.addWidget(
            hint_label(
                "Cliquez sur un ecran du schema pour le configurer. "
                "Chaque ecran garde ses reglages, meme apres un debranchement."
            )
        )

        self._diagram = MonitorDiagram()
        self._diagram.monitor_clicked.connect(self.select_monitor)
        root.addWidget(self._diagram)

        # --- Modes globaux ---
        modes = QHBoxLayout()
        modes.setSpacing(8)
        modes.addWidget(QLabel("Mode d'affichage :"))

        self._mode = QComboBox()
        self._mode.addItem("Un fond different par ecran", MODE_INDEPENDANT)
        self._mode.addItem("Le meme fond sur tous les ecrans", MODE_IDENTIQUE)
        self._mode.addItem("Image panoramique repartie", MODE_PANORAMIQUE)
        self._mode.currentIndexChanged.connect(self._on_mode_changed)
        modes.addWidget(self._mode)

        self._apply_mode = QPushButton("Appliquer le mode")
        self._apply_mode.clicked.connect(self._apply_current_mode)
        modes.addWidget(self._apply_mode)
        modes.addStretch(1)
        root.addLayout(modes)

        self._mode_hint = hint_label("")
        root.addWidget(self._mode_hint)

        # --- Reglages de l'ecran selectionne ---
        self._box = QGroupBox("Reglages de l'ecran")
        box_layout = QVBoxLayout(self._box)
        box_layout.setSpacing(10)

        self._info = QLabel("Aucun ecran selectionne")
        self._info.setWordWrap(True)
        box_layout.addWidget(self._info)

        self._current = QLabel("Fond actuel : -")
        self._current.setObjectName("hint")
        box_layout.addWidget(self._current)

        self._enabled = QCheckBox("Gerer cet ecran avec Wallpaper Studio")
        self._enabled.toggled.connect(self._save_current)
        box_layout.addWidget(self._enabled)

        fill_row = QHBoxLayout()
        fill_row.addWidget(QLabel("Cadrage :"))
        self._fill = QComboBox()
        for mode in FillMode:
            self._fill.addItem(mode.label, mode.value)
        self._fill.currentIndexChanged.connect(self._save_current)
        fill_row.addWidget(self._fill)
        fill_row.addStretch(1)
        box_layout.addLayout(fill_row)

        vol_row = QHBoxLayout()
        self._muted = QCheckBox("Muet")
        self._muted.toggled.connect(self._save_current)
        vol_row.addWidget(self._muted)
        vol_row.addWidget(QLabel("Volume :"))
        self._volume = QSlider(Qt.Horizontal)
        self._volume.setRange(0, 100)
        self._volume.setFixedWidth(180)
        self._volume.valueChanged.connect(self._on_volume)
        vol_row.addWidget(self._volume)
        self._volume_label = QLabel("0 %")
        self._volume_label.setFixedWidth(42)
        vol_row.addWidget(self._volume_label)
        vol_row.addStretch(1)
        box_layout.addLayout(vol_row)

        speed_row = QHBoxLayout()
        speed_row.addWidget(QLabel("Vitesse :"))
        self._speed = QSlider(Qt.Horizontal)
        self._speed.setRange(25, 200)
        self._speed.setValue(100)
        self._speed.setFixedWidth(180)
        self._speed.valueChanged.connect(self._on_speed)
        speed_row.addWidget(self._speed)
        self._speed_label = QLabel("1.00 x")
        self._speed_label.setFixedWidth(52)
        speed_row.addWidget(self._speed_label)
        speed_row.addStretch(1)
        box_layout.addLayout(speed_row)

        actions = QHBoxLayout()
        actions.setSpacing(8)

        self._btn_apply = QPushButton("  Appliquer la selection")
        self._btn_apply.setObjectName("primary")
        self._btn_apply.setIcon(icon("lecture"))
        self._btn_apply.clicked.connect(
            lambda: self._selected and self.apply_to_monitor.emit(self._selected)
        )
        actions.addWidget(self._btn_apply)

        self._btn_pause = QPushButton("  Mettre en pause")
        self._btn_pause.setIcon(icon("pause"))
        self._btn_pause.setCheckable(True)
        self._btn_pause.toggled.connect(self._on_pause_toggled)
        actions.addWidget(self._btn_pause)

        self._btn_restore = QPushButton("Fond precedent")
        self._btn_restore.clicked.connect(
            lambda: self._selected and self.restore_previous.emit(self._selected)
        )
        actions.addWidget(self._btn_restore)

        self._btn_clear = QPushButton("Retirer le fond")
        self._btn_clear.clicked.connect(
            lambda: self._selected and self.clear_monitor.emit(self._selected)
        )
        actions.addWidget(self._btn_clear)
        actions.addStretch(1)
        box_layout.addLayout(actions)

        root.addWidget(self._box)
        root.addStretch(1)
        self._on_mode_changed()

    # --- Donnees -----------------------------------------------------------
    def refresh(self) -> None:
        """Recharge la liste des ecrans et le schema."""
        monitors = self._engine.monitor_manager.monitors
        labels: Dict[str, str] = {}
        for monitor in monitors:
            state = self._engine.state_for(monitor.key)
            if state and state.request:
                media = self._repos.media.get_by_path(state.request.path)
                labels[monitor.key] = (
                    media.title if media else state.request.path.split("\\")[-1]
                )
        self._diagram.set_monitors(monitors, labels)

        count = len(monitors)
        self._count_badge.setText(
            f"{count} ecran detecte" if count == 1 else f"{count} ecrans detectes"
        )

        if self._selected not in {m.key for m in monitors}:
            self._selected = monitors[0].key if monitors else None
        self._diagram.set_selected(self._selected)
        self._load_selected()

    def select_monitor(self, monitor_key: str) -> None:
        self._selected = monitor_key
        self._diagram.set_selected(monitor_key)
        self._load_selected()

    def _load_selected(self) -> None:
        """Remplit le panneau de reglages depuis la base."""
        monitor = (
            self._engine.monitor_manager.by_key(self._selected) if self._selected else None
        )
        has = monitor is not None
        self._box.setEnabled(has)
        for widget in (
            self._btn_apply, self._btn_pause, self._btn_restore, self._btn_clear
        ):
            widget.setEnabled(has)

        if not has:
            self._info.setText("Aucun ecran selectionne")
            self._current.setText("Fond actuel : -")
            return

        config = self._repos.monitors.get_or_create(
            monitor.key, monitor.device, monitor.name
        )

        self._loading = True
        try:
            self._info.setText(
                f"<b>{monitor.label}</b> - {monitor.name}<br>"
                f"Resolution : {monitor.resolution_text} - "
                f"{monitor.refresh_hz} Hz - {monitor.orientation}<br>"
                f"Position : x={monitor.rect[0]}, y={monitor.rect[1]} - "
                f"Mise a l'echelle : {int(monitor.scale * 100)} %"
            )
            state = self._engine.state_for(monitor.key)
            if state and state.request:
                media = self._repos.media.get_by_path(state.request.path)
                name = media.title if media else state.request.path
                status = "en pause" if state.paused else "en lecture"
                if state.error:
                    status = f"erreur : {state.error}"
                self._current.setText(f"Fond actuel : {name} ({status})")
            else:
                self._current.setText("Fond actuel : aucun")

            self._enabled.setChecked(config.enabled)
            index = self._fill.findData(config.fill_mode.value)
            self._fill.setCurrentIndex(max(0, index))
            self._muted.setChecked(config.muted)
            self._volume.setValue(config.volume)
            self._volume_label.setText(f"{config.volume} %")
            self._speed.setValue(int(config.speed * 100))
            self._speed_label.setText(f"{config.speed:.2f} x")
            self._btn_pause.blockSignals(True)
            self._btn_pause.setChecked(bool(state and state.paused))
            self._btn_pause.setText(
                "  Reprendre" if (state and state.paused) else "  Mettre en pause"
            )
            self._btn_pause.blockSignals(False)
        finally:
            self._loading = False

    def current_config(self) -> Optional[MonitorConfig]:
        if not self._selected:
            return None
        return self._repos.monitors.get(self._selected)

    def selected_key(self) -> Optional[str]:
        return self._selected

    # --- Reactions ---------------------------------------------------------
    def _on_volume(self, value: int) -> None:
        self._volume_label.setText(f"{value} %")
        if not self._loading:
            self._save_current()

    def _on_speed(self, value: int) -> None:
        self._speed_label.setText(f"{value / 100:.2f} x")
        if not self._loading:
            self._save_current()

    def _on_pause_toggled(self, paused: bool) -> None:
        if self._loading or not self._selected:
            return
        self._btn_pause.setText("  Reprendre" if paused else "  Mettre en pause")
        self.pause_monitor.emit(self._selected, paused)

    def _save_current(self) -> None:
        """Enregistre les reglages de l'ecran et les applique a chaud."""
        if self._loading or not self._selected:
            return
        config = self._repos.monitors.get_or_create(self._selected)
        config.enabled = self._enabled.isChecked()
        config.fill_mode = FillMode(self._fill.currentData())
        config.muted = self._muted.isChecked()
        config.volume = self._volume.value()
        config.speed = self._speed.value() / 100.0
        self._repos.monitors.save(config)
        self.settings_changed.emit(self._selected)

    def _redetect(self) -> None:
        changed = self._engine.refresh_monitors()
        self.refresh()
        self.notify.emit(
            "Configuration des ecrans mise a jour."
            if changed else "Aucun changement detecte.",
            "succes" if changed else "info",
        )

    def _on_mode_changed(self) -> None:
        mode = self._mode.currentData()
        hints = {
            MODE_INDEPENDANT: "Chaque ecran affiche le fond que vous lui avez attribue.",
            MODE_IDENTIQUE: "Le fond selectionne dans la bibliotheque est applique partout.",
            MODE_PANORAMIQUE: (
                "Une seule image est decoupee selon la position de chaque ecran. "
                "Fonctionne au mieux avec une image large et des ecrans alignes."
            ),
        }
        self._mode_hint.setText(hints.get(mode, ""))

    def _apply_current_mode(self) -> None:
        mode = self._mode.currentData()
        if mode == MODE_IDENTIQUE:
            self.same_on_all_requested.emit()
        elif mode == MODE_PANORAMIQUE:
            self.span_requested.emit()
        else:
            self.notify.emit(
                "Mode independant : choisissez un fond pour chaque ecran.", "info"
            )
