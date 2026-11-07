"""Widgets reutilisables de l'interface."""

from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import (
    QEasingCurve,
    QPoint,
    QPropertyAnimation,
    QRect,
    QSize,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QLayout,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ...data.models import MediaItem
from ...media.types import MediaKind
from ..theme import icon, palette_for


class FlowLayout(QLayout):
    """Disposition en flux : les elements passent a la ligne automatiquement.

    Qt ne fournit pas cette disposition en standard ; elle est indispensable
    pour une grille de vignettes qui s'adapte a la largeur de la fenetre.
    """

    def __init__(self, parent=None, margin: int = 0, spacing: int = 12):
        super().__init__(parent)
        self._items: List = []
        self._spacing = spacing
        self.setContentsMargins(margin, margin, margin, margin)

    def addItem(self, item) -> None:  # noqa: N802 - API Qt
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index):  # noqa: N802 - API Qt
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index):  # noqa: N802 - API Qt
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def expandingDirections(self):  # noqa: N802 - API Qt
        return Qt.Orientations(0)

    def hasHeightForWidth(self) -> bool:  # noqa: N802 - API Qt
        return True

    def heightForWidth(self, width: int) -> int:  # noqa: N802 - API Qt
        return self._layout(QRect(0, 0, width, 0), apply=False)

    def setGeometry(self, rect: QRect) -> None:  # noqa: N802 - API Qt
        super().setGeometry(rect)
        self._layout(rect, apply=True)

    def sizeHint(self) -> QSize:  # noqa: N802 - API Qt
        return self.minimumSize()

    def minimumSize(self) -> QSize:  # noqa: N802 - API Qt
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        return size + QSize(
            margins.left() + margins.right(), margins.top() + margins.bottom()
        )

    def _layout(self, rect: QRect, apply: bool) -> int:
        margins = self.contentsMargins()
        x = rect.x() + margins.left()
        y = rect.y() + margins.top()
        right = rect.right() - margins.right()
        line_height = 0

        for item in self._items:
            hint = item.sizeHint()
            if x + hint.width() > right and line_height > 0:
                x = rect.x() + margins.left()
                y += line_height + self._spacing
                line_height = 0
            if apply:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x += hint.width() + self._spacing
            line_height = max(line_height, hint.height())

        return y + line_height - rect.y() + margins.bottom()


class Badge(QLabel):
    """Petite pastille d'etat coloree."""

    def __init__(self, text: str = "", kind: str = "neutre", parent=None):
        super().__init__(text, parent)
        self.set_kind(kind)
        self.setAlignment(Qt.AlignCenter)

    def set_kind(self, kind: str) -> None:
        self.setObjectName(
            {
                "succes": "badgeSucces",
                "alerte": "badgeAlerte",
                "erreur": "badgeErreur",
            }.get(kind, "statusBadge")
        )
        self.style().unpolish(self)
        self.style().polish(self)


class MediaCard(QFrame):
    """Vignette d'un fond d'ecran dans la bibliotheque."""

    clicked = Signal(object)
    double_clicked = Signal(object)
    context_requested = Signal(object, QPoint)
    favorite_toggled = Signal(object)

    CARD_SIZE = QSize(236, 186)

    def __init__(self, item: MediaItem, theme: str = "sombre", parent=None):
        super().__init__(parent)
        self.item = item
        self._theme = theme
        self._selected = False
        self.setObjectName("mediaCard")
        self.setFixedSize(self.CARD_SIZE)
        self.setCursor(Qt.PointingHandCursor)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(
            lambda pos: self.context_requested.emit(self.item, self.mapToGlobal(pos))
        )

        colors = palette_for(theme)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        self._preview = QLabel()
        self._preview.setFixedHeight(116)
        self._preview.setAlignment(Qt.AlignCenter)
        self._preview.setObjectName("cardPreview")
        self._preview.setStyleSheet(
            f"QLabel#cardPreview{{background:{colors.fond_alt};border-radius:7px;"
            f"color:{colors.texte_doux};}}"
        )
        layout.addWidget(self._preview)

        self._title = QLabel(item.title)
        self._title.setStyleSheet("font-weight:600;")
        self._title.setWordWrap(False)
        self._title.setTextInteractionFlags(Qt.NoTextInteraction)
        layout.addWidget(self._title)

        row = QHBoxLayout()
        row.setSpacing(6)
        self._kind = QLabel(item.kind.label)
        self._kind.setStyleSheet(f"color:{colors.texte_doux};font-size:11px;")
        row.addWidget(self._kind)
        row.addStretch(1)

        self._meta = QLabel(self._meta_text())
        self._meta.setStyleSheet(f"color:{colors.texte_doux};font-size:11px;")
        row.addWidget(self._meta)
        layout.addLayout(row)

        self._fav = QPushButton(self)
        self._fav.setObjectName("ghost")
        self._fav.setFixedSize(28, 28)
        self._fav.move(self.CARD_SIZE.width() - 36, 12)
        self._fav.clicked.connect(lambda: self.favorite_toggled.emit(self.item))
        self._refresh_favorite()

        self.refresh_preview()
        self._update_tooltip()

    def _meta_text(self) -> str:
        if self.item.kind is MediaKind.VIDEO and self.item.duration:
            return self.item.duration_text
        if self.item.width:
            return self.item.resolution_text
        return self.item.size_text

    def _update_tooltip(self) -> None:
        lines = [
            f"<b>{self.item.title}</b>",
            f"Type : {self.item.kind.label}",
            f"Resolution : {self.item.resolution_text}",
        ]
        if self.item.duration:
            lines.append(f"Duree : {self.item.duration_text}")
        lines.append(f"Taille : {self.item.size_text}")
        if self.item.tags:
            lines.append("Tags : " + ", ".join(self.item.tags))
        lines.append(f"<span style='color:#9aa3b5'>{self.item.path}</span>")
        if self.item.missing:
            lines.append("<b style='color:#e5575f'>Fichier introuvable</b>")
        self.setToolTip("<br>".join(lines))

    def _refresh_favorite(self) -> None:
        colors = palette_for(self._theme)
        color = colors.alerte if self.item.favorite else colors.texte_doux
        self._fav.setIcon(icon("etoile", color, 17))
        self._fav.setToolTip(
            "Retirer des favoris" if self.item.favorite else "Ajouter aux favoris"
        )

    def refresh_preview(self) -> None:
        """Charge la vignette, ou affiche un texte de remplacement."""
        colors = palette_for(self._theme)
        if self.item.missing:
            self._preview.setText("Fichier introuvable")
            self._preview.setStyleSheet(
                f"QLabel#cardPreview{{background:{colors.fond_alt};"
                f"border-radius:7px;color:{colors.erreur};}}"
            )
            return
        if self.item.thumbnail:
            pixmap = QPixmap(self.item.thumbnail)
            if not pixmap.isNull():
                self._preview.setPixmap(
                    pixmap.scaled(
                        self._preview.width() or 220, 116,
                        Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation,
                    )
                )
                return
        self._preview.setText(self.item.kind.label)

    def set_selected(self, selected: bool) -> None:
        self._selected = selected
        self.setProperty("selected", "true" if selected else "false")
        self.style().unpolish(self)
        self.style().polish(self)

    def update_item(self, item: MediaItem) -> None:
        self.item = item
        self._title.setText(item.title)
        self._kind.setText(item.kind.label)
        self._meta.setText(self._meta_text())
        self._refresh_favorite()
        self.refresh_preview()
        self._update_tooltip()

    def mousePressEvent(self, event) -> None:  # noqa: N802 - API Qt
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.item)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802 - API Qt
        if event.button() == Qt.LeftButton:
            self.double_clicked.emit(self.item)
        super().mouseDoubleClickEvent(event)


class Toast(QFrame):
    """Notification discrete, affichee en bas a droite de la fenetre."""

    def __init__(self, parent: QWidget, message: str, kind: str = "info",
                 duration: int = 3200):
        super().__init__(parent)
        colors = palette_for("sombre")
        bar = {
            "succes": colors.succes, "erreur": colors.erreur,
            "alerte": colors.alerte,
        }.get(kind, colors.accent)

        self.setObjectName("card")
        self.setStyleSheet(
            f"#card{{background:{colors.surface_haut};"
            f"border:1px solid {colors.bordure};border-left:4px solid {bar};"
            f"border-radius:9px;}}"
        )
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 11, 14, 11)
        label = QLabel(message)
        label.setWordWrap(True)
        label.setMaximumWidth(380)
        layout.addWidget(label)

        self._effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._effect)
        self._effect.setOpacity(0.0)

        self.adjustSize()
        self._reposition()

        self._fade_in = QPropertyAnimation(self._effect, b"opacity", self)
        self._fade_in.setDuration(180)
        self._fade_in.setStartValue(0.0)
        self._fade_in.setEndValue(1.0)
        self._fade_in.setEasingCurve(QEasingCurve.OutCubic)
        self._fade_in.start()

        QTimer.singleShot(duration, self._dismiss)
        self.show()
        self.raise_()

    def _reposition(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        self.move(
            parent.width() - self.width() - 24,
            parent.height() - self.height() - 24,
        )

    def _dismiss(self) -> None:
        self._fade_out = QPropertyAnimation(self._effect, b"opacity", self)
        self._fade_out.setDuration(260)
        self._fade_out.setStartValue(1.0)
        self._fade_out.setEndValue(0.0)
        self._fade_out.finished.connect(self.deleteLater)
        self._fade_out.start()


class MonitorDiagram(QWidget):
    """Representation visuelle de la disposition des ecrans.

    Les rectangles respectent les proportions et les positions reelles du
    bureau virtuel, y compris les coordonnees negatives.
    """

    monitor_clicked = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._monitors: List = []
        self._selected: Optional[str] = None
        self._labels = {}
        self.setMinimumHeight(190)
        self.setCursor(Qt.PointingHandCursor)

    def set_monitors(self, monitors: List, labels: Optional[dict] = None) -> None:
        self._monitors = list(monitors)
        self._labels = labels or {}
        self.update()

    def set_selected(self, monitor_key: Optional[str]) -> None:
        self._selected = monitor_key
        self.update()

    def _bounds(self):
        if not self._monitors:
            return None
        left = min(m.rect[0] for m in self._monitors)
        top = min(m.rect[1] for m in self._monitors)
        right = max(m.rect[0] + m.rect[2] for m in self._monitors)
        bottom = max(m.rect[1] + m.rect[3] for m in self._monitors)
        return left, top, right - left, bottom - top

    def _screen_rects(self):
        """Rectangles a l'echelle du widget, avec leur cle d'ecran."""
        bounds = self._bounds()
        if not bounds:
            return []
        bx, by, bw, bh = bounds
        margin = 16
        avail_w = max(1, self.width() - 2 * margin)
        avail_h = max(1, self.height() - 2 * margin)
        scale = min(avail_w / max(1, bw), avail_h / max(1, bh))
        off_x = margin + (avail_w - bw * scale) / 2
        off_y = margin + (avail_h - bh * scale) / 2

        out = []
        for m in self._monitors:
            x, y, w, h = m.rect
            out.append(
                (
                    m,
                    QRect(
                        int(off_x + (x - bx) * scale),
                        int(off_y + (y - by) * scale),
                        max(24, int(w * scale)),
                        max(18, int(h * scale)),
                    ),
                )
            )
        return out

    def mousePressEvent(self, event) -> None:  # noqa: N802 - API Qt
        for monitor, rect in self._screen_rects():
            if rect.contains(event.position().toPoint()):
                self.monitor_clicked.emit(monitor.key)
                return
        super().mousePressEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802 - API Qt
        colors = palette_for("sombre")
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        rects = self._screen_rects()
        if not rects:
            painter.setPen(QColor(colors.texte_doux))
            painter.drawText(self.rect(), Qt.AlignCenter, "Aucun ecran detecte")
            return

        for monitor, rect in rects:
            selected = monitor.key == self._selected
            painter.setBrush(
                QColor(colors.accent_sombre) if selected else QColor(colors.surface_haut)
            )
            pen = QPen(QColor(colors.accent if selected else colors.bordure))
            pen.setWidth(2 if selected else 1)
            painter.setPen(pen)
            painter.drawRoundedRect(rect, 8, 8)

            painter.setPen(QColor(colors.texte))
            font = QFont()
            font.setPointSize(10)
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(
                rect.adjusted(6, 6, -6, -rect.height() // 2),
                Qt.AlignLeft | Qt.AlignTop,
                f"Ecran {monitor.index + 1}" + (" *" if monitor.is_primary else ""),
            )

            font.setBold(False)
            font.setPointSize(8)
            painter.setFont(font)
            painter.setPen(QColor(colors.texte_doux))
            detail = f"{monitor.width}x{monitor.height}"
            assigned = self._labels.get(monitor.key)
            if assigned:
                detail += f"\n{assigned}"
            painter.drawText(
                rect.adjusted(6, rect.height() // 2 - 6, -6, -6),
                Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap,
                detail,
            )


def section_title(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("sectionTitle")
    return label


def hint_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("hint")
    label.setWordWrap(True)
    return label


def card(layout_cls=QVBoxLayout) -> tuple:
    """Cree un panneau « carte » et retourne ``(widget, layout)``."""
    frame = QFrame()
    frame.setObjectName("card")
    layout = layout_cls(frame)
    layout.setContentsMargins(16, 16, 16, 16)
    layout.setSpacing(10)
    return frame, layout
