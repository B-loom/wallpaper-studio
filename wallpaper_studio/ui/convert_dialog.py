"""Boite de dialogue de conversion de medias (module facultatif FFmpeg)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from ..media import converter
from ..media.converter import ConversionType
from ..media.types import MediaKind
from .widgets.common import hint_label

log = logging.getLogger(__name__)


class ConversionWorker(QThread):
    """Execute la conversion sans bloquer l'interface."""

    progress = Signal(int)
    done = Signal(object)

    def __init__(self, kind: ConversionType, source: Path, destination: Path,
                 options: dict, parent=None):
        super().__init__(parent)
        self._kind = kind
        self._source = source
        self._destination = destination
        self._options = options

    def run(self) -> None:
        def on_progress(fraction: float) -> None:
            self.progress.emit(int(fraction * 100))

        try:
            if self._kind is ConversionType.VIDEO_TO_GIF:
                result = converter.video_to_gif(
                    self._source, self._destination,
                    fps=self._options.get("fps", 15),
                    width=self._options.get("width", 640),
                    on_progress=on_progress,
                )
            elif self._kind is ConversionType.GIF_TO_FRAMES:
                result = converter.gif_to_frames(self._source, self._destination)
            elif self._kind is ConversionType.EXTRACT_FRAME:
                result = converter.extract_frame(
                    self._source, self._destination,
                    position=self._options.get("position", 1.0),
                )
            elif self._kind is ConversionType.CONVERT_IMAGE:
                result = converter.convert_image(self._source, self._destination)
            elif self._kind is ConversionType.FRAMES_TO_VIDEO:
                result = converter.frames_to_video(
                    str(self._source), self._destination,
                    fps=self._options.get("fps", 30), on_progress=on_progress,
                )
            else:
                result = converter.reencode_video(
                    self._source, self._destination,
                    width=self._options.get("width") or None,
                    on_progress=on_progress,
                )
        except Exception as exc:  # noqa: BLE001
            log.exception("Conversion impossible")
            result = converter.ConversionResult(False, message=str(exc))
        self.done.emit(result)


class ConvertDialog(QDialog):
    """Conversion d'un media vers un autre format."""

    converted = Signal(object)   # chemin du fichier produit

    def __init__(self, source: Path, kind: MediaKind, parent=None):
        super().__init__(parent)
        self._source = Path(source)
        self._media_kind = kind
        self._worker: Optional[ConversionWorker] = None

        self.setWindowTitle("Convertir un media")
        self.setMinimumWidth(500)
        self._build()
        self._on_type_changed()

    def _build(self) -> None:
        layout = QVBoxLayout(self)

        if not converter.is_available():
            layout.addWidget(
                QLabel(
                    "<b>FFmpeg est introuvable.</b><br>"
                    "Installez FFmpeg ou placez ffmpeg.exe dans un sous-dossier "
                    "<i>ffmpeg</i> a cote de l'application pour activer les "
                    "conversions video."
                )
            )
            buttons = QDialogButtonBox(QDialogButtonBox.Close)
            buttons.rejected.connect(self.reject)
            layout.addWidget(buttons)
            return

        form = QFormLayout()
        form.addRow("Fichier source :", QLabel(self._source.name))

        self._type = QComboBox()
        for conversion in self._relevant_types():
            self._type.addItem(conversion.label, conversion)
        self._type.currentIndexChanged.connect(self._on_type_changed)
        form.addRow("Conversion :", self._type)

        self._fps = QSpinBox()
        self._fps.setRange(1, 60)
        self._fps.setValue(15)
        form.addRow("Images par seconde :", self._fps)

        self._width = QSpinBox()
        self._width.setRange(0, 3840)
        self._width.setValue(640)
        self._width.setSpecialValueText("Conserver")
        form.addRow("Largeur :", self._width)

        self._position = QSpinBox()
        self._position.setRange(0, 86400)
        self._position.setValue(1)
        self._position.setSuffix(" s")
        form.addRow("Position :", self._position)

        destination_row = QHBoxLayout()
        self._destination = QLineEdit()
        destination_row.addWidget(self._destination, 1)
        browse = QPushButton("Parcourir...")
        browse.clicked.connect(self._choose_destination)
        destination_row.addWidget(browse)
        form.addRow("Destination :", destination_row)

        layout.addLayout(form)

        self._hint = hint_label("")
        layout.addWidget(self._hint)

        self._progress = QProgressBar()
        self._progress.hide()
        layout.addWidget(self._progress)

        self._buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        self._buttons.button(QDialogButtonBox.Ok).setText("Convertir")
        self._buttons.button(QDialogButtonBox.Cancel).setText("Fermer")
        self._buttons.accepted.connect(self._start)
        self._buttons.rejected.connect(self.reject)
        layout.addWidget(self._buttons)

    def _relevant_types(self):
        """Conversions ayant un sens pour ce type de media."""
        if self._media_kind is MediaKind.VIDEO:
            return [ConversionType.VIDEO_TO_GIF, ConversionType.EXTRACT_FRAME,
                    ConversionType.REENCODE_VIDEO]
        if self._media_kind is MediaKind.ANIMATED_IMAGE:
            return [ConversionType.GIF_TO_FRAMES, ConversionType.EXTRACT_FRAME]
        if self._media_kind is MediaKind.IMAGE:
            return [ConversionType.CONVERT_IMAGE, ConversionType.FRAMES_TO_VIDEO]
        return list(ConversionType)

    def _default_destination(self, conversion: ConversionType) -> Path:
        stem = self._source.stem
        folder = self._source.parent
        return {
            ConversionType.VIDEO_TO_GIF: folder / f"{stem}.gif",
            ConversionType.GIF_TO_FRAMES: folder / f"{stem}_images",
            ConversionType.EXTRACT_FRAME: folder / f"{stem}_image.png",
            ConversionType.CONVERT_IMAGE: folder / f"{stem}_converti.png",
            ConversionType.FRAMES_TO_VIDEO: folder / f"{stem}_video.mp4",
            ConversionType.REENCODE_VIDEO: folder / f"{stem}_reencode.mp4",
        }[conversion]

    def _on_type_changed(self) -> None:
        conversion = self._type.currentData()
        if conversion is None:
            return
        self._destination.setText(str(self._default_destination(conversion)))

        needs_fps = conversion in (
            ConversionType.VIDEO_TO_GIF, ConversionType.FRAMES_TO_VIDEO
        )
        needs_width = conversion in (
            ConversionType.VIDEO_TO_GIF, ConversionType.REENCODE_VIDEO
        )
        needs_position = conversion is ConversionType.EXTRACT_FRAME
        self._fps.setEnabled(needs_fps)
        self._width.setEnabled(needs_width)
        self._position.setEnabled(needs_position)

        hints = {
            ConversionType.VIDEO_TO_GIF:
                "Un GIF est bien plus lourd qu'une video a qualite egale ; "
                "reduisez la largeur et la cadence pour un fichier raisonnable.",
            ConversionType.REENCODE_VIDEO:
                "Reencoder en H.264 ameliore la fluidite si le format d'origine "
                "n'est pas accelere par la carte graphique.",
            ConversionType.FRAMES_TO_VIDEO:
                "La source doit suivre un motif numerote, par exemple "
                "image_%04d.png.",
            ConversionType.GIF_TO_FRAMES:
                "Chaque image du GIF sera enregistree en PNG dans le dossier.",
        }
        self._hint.setText(hints.get(conversion, ""))

    def _choose_destination(self) -> None:
        conversion = self._type.currentData()
        if conversion is ConversionType.GIF_TO_FRAMES:
            folder = QFileDialog.getExistingDirectory(
                self, "Dossier de destination", self._destination.text()
            )
            if folder:
                self._destination.setText(folder)
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Fichier de destination", self._destination.text()
        )
        if path:
            self._destination.setText(path)

    def _start(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            return
        destination = Path(self._destination.text().strip())
        if not destination.name:
            QMessageBox.warning(self, "Destination", "Choisissez un fichier de sortie.")
            return

        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.show()
        self._buttons.button(QDialogButtonBox.Ok).setEnabled(False)

        self._worker = ConversionWorker(
            self._type.currentData(), self._source, destination,
            {
                "fps": self._fps.value(),
                "width": self._width.value(),
                "position": float(self._position.value()),
            },
        )
        self._worker.progress.connect(self._progress.setValue)
        self._worker.done.connect(self._on_done)
        self._worker.start()

    def _on_done(self, result) -> None:
        self._progress.hide()
        self._buttons.button(QDialogButtonBox.Ok).setEnabled(True)
        if result.success:
            QMessageBox.information(
                self, "Conversion terminee",
                f"{result.summary}\n\n{result.output}"
                + (f"\n{result.message}" if result.message else ""),
            )
            self.converted.emit(result.output)
            self.accept()
        else:
            QMessageBox.warning(
                self, "Echec de la conversion", result.summary
            )
