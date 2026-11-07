"""Page Performances : mesures reelles et reglages d'economie de ressources."""

from __future__ import annotations

from typing import Dict, List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from ..data.settings import QUALITE_EQUILIBRE, QUALITE_PERFORMANCE, QUALITE_QUALITE
from ..perf.performance_manager import PerformanceSnapshot
from .theme import palette_for
from .widgets.common import Badge, hint_label


class Sparkline(QWidget):
    """Petite courbe d'historique, sans dependance externe."""

    def __init__(self, maximum: float = 100.0, unit: str = "%", parent=None):
        super().__init__(parent)
        self._values: List[float] = []
        self._max = maximum
        self._unit = unit
        self.setMinimumHeight(54)

    def push(self, value: Optional[float]) -> None:
        if value is None:
            return
        self._values.append(float(value))
        # 90 points = 3 minutes a un releve toutes les 2 secondes.
        if len(self._values) > 90:
            self._values.pop(0)
        self._max = max(self._max, max(self._values) if self._values else 0)
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - API Qt
        colors = palette_for("sombre")
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.fillRect(self.rect(), QColor(colors.fond_alt))

        if len(self._values) < 2:
            painter.setPen(QColor(colors.texte_doux))
            painter.drawText(self.rect(), Qt.AlignCenter, "Mesure en cours...")
            return

        width, height = self.width(), self.height()
        ceiling = max(1.0, self._max)
        step = width / max(1, len(self._values) - 1)

        pen = QPen(QColor(colors.accent))
        pen.setWidth(2)
        painter.setPen(pen)
        points = [
            (i * step, height - (v / ceiling) * (height - 8) - 4)
            for i, v in enumerate(self._values)
        ]
        for i in range(len(points) - 1):
            painter.drawLine(
                int(points[i][0]), int(points[i][1]),
                int(points[i + 1][0]), int(points[i + 1][1]),
            )

        painter.setPen(QColor(colors.texte_doux))
        painter.drawText(
            4, 14, f"max {ceiling:.0f}{self._unit}  -  actuel {self._values[-1]:.0f}{self._unit}"
        )


class MetricTile(QWidget):
    """Tuile affichant une mesure et son libelle."""

    def __init__(self, label: str, parent=None):
        super().__init__(parent)
        colors = palette_for("sombre")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(2)

        self._value = QLabel("-")
        self._value.setStyleSheet("font-size:21px;font-weight:600;")
        layout.addWidget(self._value)

        caption = QLabel(label)
        caption.setStyleSheet(f"color:{colors.texte_doux};font-size:11px;")
        layout.addWidget(caption)

        self.setObjectName("metricTile")
        self.setStyleSheet(
            f"QWidget#metricTile{{background:{colors.surface};"
            f"border:1px solid {colors.bordure};border-radius:10px;}}"
        )

    def set_value(self, text: str) -> None:
        self._value.setText(text)


class PerformanceView(QWidget):
    """Page Performances."""

    notify = Signal(str, str)

    def __init__(self, engine, perf_manager, settings, parent=None):
        super().__init__(parent)
        self._engine = engine
        self._perf = perf_manager
        self._settings = settings
        self._tiles: Dict[str, MetricTile] = {}
        self._loading = False
        self._build()
        perf_manager.snapshot_ready.connect(self.update_snapshot)
        # Le releve ne tourne que tant que cette page est affichee.
        perf_manager.set_measuring(True)

    def set_updates_active(self, active: bool) -> None:
        self._perf.set_measuring(active and self.isVisible())

    def showEvent(self, event):  # noqa: N802 - API Qt
        super().showEvent(event)
        self._perf.set_measuring(True)

    def hideEvent(self, event):  # noqa: N802 - API Qt
        super().hideEvent(event)
        self._perf.set_measuring(False)

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(14)

        header = QHBoxLayout()
        title = QLabel("Performances")
        title.setObjectName("pageTitle")
        header.addWidget(title)
        header.addStretch(1)
        self._pause_badge = Badge("Lecture", "succes")
        header.addWidget(self._pause_badge)
        root.addLayout(header)

        # --- Tuiles de mesure ---
        grid = QGridLayout()
        grid.setSpacing(10)
        for index, (key, label) in enumerate(
            [
                ("ram", "Memoire utilisee"),
                ("cpu", "Processeur (application)"),
                ("sys_cpu", "Processeur (systeme)"),
                ("gpu", "Charge GPU"),
                ("fps", "Images par seconde"),
                ("actifs", "Fonds actifs"),
                ("animes", "Rendus animes"),
                ("alim", "Alimentation"),
            ]
        ):
            tile = MetricTile(label)
            self._tiles[key] = tile
            grid.addWidget(tile, index // 4, index % 4)
        root.addLayout(grid)

        root.addWidget(
            hint_label(
                "La charge GPU n'est pas mesurable sans bibliotheque constructeur "
                "dediee : elle est donc indiquee comme non mesuree plutot "
                "qu'estimee au hasard."
            )
        )

        # --- Courbes ---
        charts = QHBoxLayout()
        charts.setSpacing(12)
        for key, label, unit, maximum in (
            ("cpu_chart", "Processeur de l'application", " %", 25.0),
            ("ram_chart", "Memoire (Mo)", "", 300.0),
        ):
            box = QGroupBox(label)
            box_layout = QVBoxLayout(box)
            chart = Sparkline(maximum, unit)
            setattr(self, f"_{key}", chart)
            box_layout.addWidget(chart)
            charts.addWidget(box)
        root.addLayout(charts)

        # --- Reglages ---
        settings_box = QGroupBox("Economies de ressources")
        form = QVBoxLayout(settings_box)

        quality_row = QHBoxLayout()
        quality_row.addWidget(QLabel("Profil :"))
        self._quality = QComboBox()
        self._quality.addItem("Economie d'energie (20 FPS)", QUALITE_PERFORMANCE)
        self._quality.addItem("Equilibre (30 FPS)", QUALITE_EQUILIBRE)
        self._quality.addItem("Qualite (60 FPS)", QUALITE_QUALITE)
        index = self._quality.findData(self._settings.get("qualite"))
        self._quality.setCurrentIndex(max(0, index))
        self._quality.currentIndexChanged.connect(self._change_quality)
        quality_row.addWidget(self._quality)
        quality_row.addStretch(1)
        form.addLayout(quality_row)

        fps_row = QHBoxLayout()
        fps_row.addWidget(QLabel("Plafond d'images par seconde :"))
        self._fps = QSlider(Qt.Horizontal)
        self._fps.setRange(5, 60)
        self._fps.setValue(int(self._settings.get("limite_fps", 30)))
        self._fps.setFixedWidth(220)
        self._fps.valueChanged.connect(self._change_fps)
        fps_row.addWidget(self._fps)
        self._fps_label = QLabel(f"{self._fps.value()} FPS")
        self._fps_label.setFixedWidth(60)
        fps_row.addWidget(self._fps_label)
        fps_row.addStretch(1)
        form.addLayout(fps_row)

        self._checks = {}
        for key, label in (
            ("pause_si_jeu_plein_ecran",
             "Mettre en pause quand une application occupe tout l'ecran (jeux, videos)"),
            ("pause_si_fenetre_maximisee",
             "Mettre en pause quand une fenetre est maximisee"),
            ("pause_si_batterie", "Mettre en pause sur batterie"),
            ("pause_si_session_verrouillee", "Mettre en pause quand la session est verrouillee"),
            ("decodage_materiel", "Utiliser le decodage video materiel"),
        ):
            box = QCheckBox(label)
            box.setChecked(bool(self._settings.get(key)))
            box.toggled.connect(lambda checked, k=key: self._toggle(k, checked))
            form.addWidget(box)
            self._checks[key] = box

        root.addWidget(settings_box)

        actions = QHBoxLayout()
        self._btn_pause = QPushButton("Mettre tous les fonds en pause")
        self._btn_pause.clicked.connect(self._toggle_pause)
        actions.addWidget(self._btn_pause)
        actions.addStretch(1)
        root.addLayout(actions)
        root.addStretch(1)

    # --- Mise a jour -------------------------------------------------------
    def update_snapshot(self, snapshot: PerformanceSnapshot) -> None:
        self._tiles["ram"].set_value(snapshot.ram_text)
        self._tiles["cpu"].set_value(snapshot.cpu_text)
        self._tiles["sys_cpu"].set_value(snapshot.system_cpu_text)
        self._tiles["gpu"].set_value(snapshot.gpu_text)
        self._tiles["fps"].set_value(snapshot.fps_text)
        self._tiles["actifs"].set_value(str(snapshot.active_wallpapers))
        self._tiles["animes"].set_value(str(snapshot.animated_wallpapers))
        self._tiles["alim"].set_value(
            snapshot.power.description if snapshot.power else "-"
        )

        self._cpu_chart.push(snapshot.cpu_percent)
        self._ram_chart.push(snapshot.ram_mb)

        if snapshot.paused:
            reason = snapshot.pause_reason or "pause manuelle"
            self._pause_badge.setText(f"En pause - {reason}")
            self._pause_badge.set_kind("alerte")
            self._btn_pause.setText("Reprendre la lecture")
        else:
            self._pause_badge.setText("Lecture")
            self._pause_badge.set_kind("succes")
            self._btn_pause.setText("Mettre tous les fonds en pause")

    def refresh_from_settings(self) -> None:
        self._loading = True
        for key, box in self._checks.items():
            box.setChecked(bool(self._settings.get(key)))
        self._fps.setValue(int(self._settings.get("limite_fps", 30)))
        index = self._quality.findData(self._settings.get("qualite"))
        self._quality.setCurrentIndex(max(0, index))
        self._loading = False

    # --- Actions -----------------------------------------------------------
    def _change_quality(self) -> None:
        if self._loading:
            return
        profile = self._quality.currentData()
        self._settings.set("qualite", profile)
        self._perf.apply_quality_profile(profile)
        self._fps.setValue(int(self._settings.get("limite_fps", 30)))
        self.notify.emit(f"Profil « {self._quality.currentText()} » applique.", "succes")

    def _change_fps(self, value: int) -> None:
        self._fps_label.setText(f"{value} FPS")
        if self._loading:
            return
        self._settings.set("limite_fps", value)
        self._engine.set_fps_cap(value)

    def _toggle(self, key: str, checked: bool) -> None:
        if self._loading:
            return
        self._settings.set(key, checked)
        if key == "decodage_materiel":
            self._engine.set_hardware_decode(checked)
            self.notify.emit(
                "Decodage materiel " + ("active" if checked else "desactive")
                + " ; les videos en cours ont ete relancees.",
                "succes",
            )

    def _toggle_pause(self) -> None:
        if self._engine.is_paused:
            self._perf.force_resume()
            self.notify.emit("Lecture reprise.", "succes")
        else:
            self._engine.pause_all("demande manuelle")
            self.notify.emit("Tous les fonds sont en pause.", "info")
        self.update_snapshot(self._perf.measure())
