"""Editeur : recadrage, colorimetrie, effets et presets, avec apercu direct."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..data.models import MediaItem, adjustments_from_json, adjustments_to_json
from ..engine.effects import available_effects
from ..engine.playback import EffectConfig, ImageAdjustments
from ..media.image_ops import load_static_image
from ..media.types import FillMode, MediaKind
from .theme import icon
from .widgets.common import hint_label, section_title

log = logging.getLogger(__name__)

#: Taille de l'apercu : volontairement modeste pour rester fluide.
PREVIEW_MAX = 760


class EditorView(QWidget):
    """Page Editeur."""

    apply_requested = Signal(object, object, object, object)  # item, adj, fill, effets
    notify = Signal(str, str)

    def __init__(self, repos, settings, parent=None):
        super().__init__(parent)
        self._repos = repos
        self._settings = settings
        self._item: Optional[MediaItem] = None
        self._loading = False

        # L'apercu est recalcule apres une courte pause : deplacer un curseur
        # ne declenche donc pas un traitement d'image par pixel bouge.
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(140)
        self._debounce.timeout.connect(self._render_preview)

        self._build()

    # --- Construction ------------------------------------------------------
    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(14)

        header = QHBoxLayout()
        title = QLabel("Editeur")
        title.setObjectName("pageTitle")
        header.addWidget(title)
        header.addStretch(1)

        self._preset = QComboBox()
        self._preset.setMinimumWidth(180)
        self._preset.currentIndexChanged.connect(self._load_preset)
        header.addWidget(self._preset)

        save_preset = QPushButton("Enregistrer le preset")
        save_preset.clicked.connect(self._save_preset)
        header.addWidget(save_preset)

        delete_preset = QPushButton("Supprimer")
        delete_preset.setObjectName("ghost")
        delete_preset.clicked.connect(self._delete_preset)
        header.addWidget(delete_preset)
        root.addLayout(header)

        body = QHBoxLayout()
        body.setSpacing(16)

        # --- Apercu ---
        preview_box = QVBoxLayout()
        self._preview = QLabel("Choisissez un fond dans la bibliotheque")
        self._preview.setAlignment(Qt.AlignCenter)
        self._preview.setMinimumSize(520, 310)
        self._preview.setStyleSheet(
            "background:#0d0f14;border:1px solid #2f3542;border-radius:10px;color:#9aa3b5;"
        )
        preview_box.addWidget(self._preview, 1)

        self._caption = hint_label("")
        preview_box.addWidget(self._caption)
        body.addLayout(preview_box, 3)

        # --- Reglages ---
        panel = QScrollArea()
        panel.setWidgetResizable(True)
        panel.setFixedWidth(330)
        content = QWidget()
        side = QVBoxLayout(content)
        side.setSpacing(12)
        side.setContentsMargins(4, 4, 12, 4)

        # Geometrie
        geo = QGroupBox("Geometrie")
        geo_layout = QVBoxLayout(geo)
        fill_row = QHBoxLayout()
        fill_row.addWidget(QLabel("Cadrage :"))
        self._fill = QComboBox()
        for mode in FillMode:
            self._fill.addItem(mode.label, mode.value)
        self._fill.currentIndexChanged.connect(self._schedule_preview)
        fill_row.addWidget(self._fill, 1)
        geo_layout.addLayout(fill_row)

        rot_row = QHBoxLayout()
        rot_row.addWidget(QLabel("Rotation :"))
        self._rotation = QComboBox()
        for angle in (0, 90, 180, 270):
            self._rotation.addItem(f"{angle}°", angle)
        self._rotation.currentIndexChanged.connect(self._schedule_preview)
        rot_row.addWidget(self._rotation, 1)
        geo_layout.addLayout(rot_row)

        flips = QHBoxLayout()
        self._flip_h = QCheckBox("Miroir horizontal")
        self._flip_v = QCheckBox("Miroir vertical")
        self._flip_h.toggled.connect(self._schedule_preview)
        self._flip_v.toggled.connect(self._schedule_preview)
        flips.addWidget(self._flip_h)
        flips.addWidget(self._flip_v)
        geo_layout.addLayout(flips)
        side.addWidget(geo)

        # Couleurs
        colors = QGroupBox("Couleurs")
        colors_layout = QVBoxLayout(colors)
        self._sliders = {}
        for key, label, lo, hi, default in (
            ("brightness", "Luminosite", 20, 200, 100),
            ("contrast", "Contraste", 20, 200, 100),
            ("saturation", "Saturation", 0, 200, 100),
            ("hue", "Teinte", -180, 180, 0),
            ("blur", "Flou", 0, 40, 0),
        ):
            row = QHBoxLayout()
            name = QLabel(label)
            name.setFixedWidth(88)
            row.addWidget(name)
            slider = QSlider(Qt.Horizontal)
            slider.setRange(lo, hi)
            slider.setValue(default)
            slider.valueChanged.connect(self._schedule_preview)
            row.addWidget(slider, 1)
            value = QLabel()
            value.setFixedWidth(46)
            value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            row.addWidget(value)
            colors_layout.addLayout(row)
            self._sliders[key] = (slider, value, default)
            slider.valueChanged.connect(
                lambda v, k=key: self._update_slider_label(k, v)
            )
            self._update_slider_label(key, default)

        reset = QPushButton("Reinitialiser les couleurs")
        reset.setObjectName("ghost")
        reset.clicked.connect(self._reset_colors)
        colors_layout.addWidget(reset)
        side.addWidget(colors)

        # Lecture
        self._playback = QGroupBox("Lecture")
        play_layout = QVBoxLayout(self._playback)
        speed_row = QHBoxLayout()
        speed_row.addWidget(QLabel("Vitesse :"))
        self._speed = QDoubleSpinBox()
        self._speed.setRange(0.25, 4.0)
        self._speed.setSingleStep(0.05)
        self._speed.setValue(1.0)
        self._speed.setSuffix(" x")
        speed_row.addWidget(self._speed, 1)
        play_layout.addLayout(speed_row)

        vol_row = QHBoxLayout()
        self._muted = QCheckBox("Muet")
        self._muted.setChecked(True)
        vol_row.addWidget(self._muted)
        vol_row.addWidget(QLabel("Volume :"))
        self._volume = QSpinBox()
        self._volume.setRange(0, 100)
        self._volume.setSuffix(" %")
        vol_row.addWidget(self._volume, 1)
        play_layout.addLayout(vol_row)
        side.addWidget(self._playback)

        # Effets
        effects_box = QGroupBox("Effets superposes")
        effects_layout = QVBoxLayout(effects_box)
        effects_layout.addWidget(
            hint_label("Chaque effet coche est reellement dessine sur le fond.")
        )
        self._effects = {}
        for name, label in available_effects():
            row = QHBoxLayout()
            box = QCheckBox(label)
            box.setFixedWidth(130)
            row.addWidget(box)
            slider = QSlider(Qt.Horizontal)
            slider.setRange(5, 100)
            slider.setValue(50)
            slider.setEnabled(False)
            box.toggled.connect(slider.setEnabled)
            row.addWidget(slider, 1)
            effects_layout.addLayout(row)
            self._effects[name] = (box, slider)
        side.addWidget(effects_box)

        side.addStretch(1)
        panel.setWidget(content)
        body.addWidget(panel)
        root.addLayout(body, 1)

        # --- Actions ---
        actions = QHBoxLayout()
        actions.addWidget(
            hint_label("Les modifications ne touchent jamais le fichier d'origine.")
        )
        actions.addStretch(1)

        revert = QPushButton("Tout reinitialiser")
        revert.clicked.connect(self._reset_all)
        actions.addWidget(revert)

        self._btn_apply = QPushButton("  Appliquer au fond d'ecran")
        self._btn_apply.setObjectName("primary")
        self._btn_apply.setIcon(icon("lecture"))
        self._btn_apply.setEnabled(False)
        self._btn_apply.clicked.connect(self._apply)
        actions.addWidget(self._btn_apply)
        root.addLayout(actions)

        self._reload_presets()

    # --- Helpers -----------------------------------------------------------
    def _update_slider_label(self, key: str, value: int) -> None:
        slider, label, _ = self._sliders[key]
        if key == "hue":
            label.setText(f"{value}°")
        elif key == "blur":
            label.setText(f"{value} px")
        else:
            label.setText(f"{value} %")

    def _reset_colors(self) -> None:
        for key, (slider, _, default) in self._sliders.items():
            slider.setValue(default)

    def _reset_all(self) -> None:
        self._reset_colors()
        self._rotation.setCurrentIndex(0)
        self._flip_h.setChecked(False)
        self._flip_v.setChecked(False)
        self._fill.setCurrentIndex(0)
        self._speed.setValue(1.0)
        self._volume.setValue(0)
        self._muted.setChecked(True)
        for box, slider in self._effects.values():
            box.setChecked(False)
            slider.setValue(50)
        self._schedule_preview()

    def adjustments(self) -> ImageAdjustments:
        return ImageAdjustments(
            brightness=self._sliders["brightness"][0].value() / 100.0,
            contrast=self._sliders["contrast"][0].value() / 100.0,
            saturation=self._sliders["saturation"][0].value() / 100.0,
            hue=float(self._sliders["hue"][0].value()),
            blur=float(self._sliders["blur"][0].value()),
            rotation=self._rotation.currentData(),
            flip_h=self._flip_h.isChecked(),
            flip_v=self._flip_v.isChecked(),
        )

    def effects(self) -> tuple:
        return tuple(
            EffectConfig(name=name, enabled=True, intensity=slider.value() / 100.0)
            for name, (box, slider) in self._effects.items()
            if box.isChecked()
        )

    def fill_mode(self) -> FillMode:
        return FillMode(self._fill.currentData())

    # --- Chargement d'un media --------------------------------------------
    def load_item(self, item: MediaItem) -> None:
        """Ouvre un fond dans l'editeur."""
        self._item = item
        self._btn_apply.setEnabled(True)
        self._playback.setEnabled(item.kind in (MediaKind.VIDEO, MediaKind.ANIMATED_IMAGE))

        self._caption.setText(
            f"{item.title} - {item.kind.label} - {item.resolution_text}"
        )
        if item.missing:
            self._preview.setText("Fichier introuvable")
            self._preview.setPixmap(QPixmap())
            return
        self._render_preview()

    def _schedule_preview(self) -> None:
        if not self._loading:
            self._debounce.start()

    def _render_preview(self) -> None:
        """Calcule l'apercu avec les corrections courantes."""
        if self._item is None or self._item.missing:
            return

        item = self._item
        try:
            if item.kind is MediaKind.VIDEO:
                # Pour une video, on travaille sur la vignette : decoder la
                # video a chaque mouvement de curseur serait trop couteux.
                source = item.thumbnail
                if not source or not Path(source).exists():
                    self._preview.setText(
                        "Apercu indisponible\n(vignette video absente)"
                    )
                    return
            else:
                source = item.path

            image = load_static_image(
                source, adjustments=self.adjustments(), max_side=PREVIEW_MAX
            )
            pixmap = QPixmap.fromImage(image)
            self._preview.setPixmap(
                pixmap.scaled(
                    self._preview.width() - 8, self._preview.height() - 8,
                    Qt.KeepAspectRatio, Qt.SmoothTransformation,
                )
            )
            self._preview.setText("")
        except Exception as exc:  # noqa: BLE001
            log.exception("Apercu impossible")
            self._preview.setPixmap(QPixmap())
            self._preview.setText(f"Apercu impossible :\n{exc}")

    def resizeEvent(self, event) -> None:  # noqa: N802 - API Qt
        super().resizeEvent(event)
        self._schedule_preview()

    def _apply(self) -> None:
        if self._item is None:
            return
        self.apply_requested.emit(
            self._item, self.adjustments(), self.fill_mode(), self.effects()
        )

    # --- Presets -----------------------------------------------------------
    def _reload_presets(self) -> None:
        self._loading = True
        self._preset.clear()
        self._preset.addItem("Aucun preset", None)
        for preset_id, name, payload in self._repos.presets.list():
            self._preset.addItem(name, (preset_id, payload))
        self._loading = False

    def _save_preset(self) -> None:
        name, ok = QInputDialog.getText(self, "Enregistrer le preset", "Nom :")
        if not ok or not name.strip():
            return
        payload = json.dumps(
            {
                "adjustments": json.loads(adjustments_to_json(self.adjustments())),
                "fill_mode": self.fill_mode().value,
                "speed": self._speed.value(),
                "volume": self._volume.value(),
                "muted": self._muted.isChecked(),
                "effects": [
                    {"name": e.name, "intensity": e.intensity} for e in self.effects()
                ],
            }
        )
        self._repos.presets.save(name.strip(), payload)
        self._reload_presets()
        self.notify.emit(f"Preset « {name.strip()} » enregistre.", "succes")

    def _load_preset(self) -> None:
        if self._loading:
            return
        data = self._preset.currentData()
        if not data:
            return
        _, payload = data
        try:
            parsed = json.loads(payload)
        except ValueError:
            self.notify.emit("Preset illisible.", "erreur")
            return

        self._loading = True
        try:
            adj = adjustments_from_json(json.dumps(parsed.get("adjustments", {})))
            self._sliders["brightness"][0].setValue(int(adj.brightness * 100))
            self._sliders["contrast"][0].setValue(int(adj.contrast * 100))
            self._sliders["saturation"][0].setValue(int(adj.saturation * 100))
            self._sliders["hue"][0].setValue(int(adj.hue))
            self._sliders["blur"][0].setValue(int(adj.blur))
            self._rotation.setCurrentIndex(
                max(0, self._rotation.findData(adj.rotation))
            )
            self._flip_h.setChecked(adj.flip_h)
            self._flip_v.setChecked(adj.flip_v)

            index = self._fill.findData(parsed.get("fill_mode", "cover"))
            self._fill.setCurrentIndex(max(0, index))
            self._speed.setValue(float(parsed.get("speed", 1.0)))
            self._volume.setValue(int(parsed.get("volume", 0)))
            self._muted.setChecked(bool(parsed.get("muted", True)))

            wanted = {e["name"]: e.get("intensity", 0.5) for e in parsed.get("effects", [])}
            for name, (box, slider) in self._effects.items():
                box.setChecked(name in wanted)
                if name in wanted:
                    slider.setValue(int(wanted[name] * 100))
        finally:
            self._loading = False
        self._render_preview()

    def _delete_preset(self) -> None:
        data = self._preset.currentData()
        if not data:
            return
        preset_id, _ = data
        name = self._preset.currentText()
        answer = QMessageBox.question(
            self, "Supprimer le preset", f"Supprimer « {name} » ?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if answer == QMessageBox.Yes:
            self._repos.presets.delete(preset_id)
            self._reload_presets()
            self.notify.emit("Preset supprime.", "succes")
