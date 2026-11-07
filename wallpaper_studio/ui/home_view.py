"""Page d'accueil : etat du systeme, fonds actifs et acces rapides."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .. import APP_NAME, APP_VERSION
from ..system import win_desktop as wd
from .theme import icon, palette_for
from .widgets.common import Badge, card, hint_label, section_title


class ActiveWallpaperTile(QWidget):
    """Carte montrant le fond actuellement affiche sur un ecran."""

    pause_clicked = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        colors = palette_for("sombre")
        self._key: Optional[str] = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        self._thumb = QLabel()
        self._thumb.setFixedSize(132, 76)
        self._thumb.setAlignment(Qt.AlignCenter)
        self._thumb.setStyleSheet(
            f"background:{colors.fond_alt};border-radius:7px;color:{colors.texte_doux};"
        )
        layout.addWidget(self._thumb)

        info = QVBoxLayout()
        info.setSpacing(3)
        self._screen = QLabel()
        self._screen.setStyleSheet("font-weight:600;")
        info.addWidget(self._screen)
        self._title = QLabel()
        self._title.setStyleSheet(f"color:{colors.texte_doux};")
        info.addWidget(self._title)
        self._state = Badge("", "neutre")
        info.addWidget(self._state, 0, Qt.AlignLeft)
        info.addStretch(1)
        layout.addLayout(info, 1)

        # Selecteur explicite : une feuille de style sans selecteur
        # s'appliquerait aussi a tous les widgets enfants.
        self.setObjectName("activeTile")
        self.setStyleSheet(
            f"QWidget#activeTile{{background:{colors.surface};"
            f"border:1px solid {colors.bordure};border-radius:10px;}}"
        )

    def update_state(self, monitor, state, media) -> None:
        self._key = monitor.key
        self._screen.setText(f"{monitor.label} - {monitor.resolution_text}")

        if state is None or state.request is None:
            self._title.setText("Aucun fond applique")
            self._state.setText("Inactif")
            self._state.set_kind("neutre")
            self._thumb.setPixmap(QPixmap())
            self._thumb.setText("-")
            return

        self._title.setText(media.title if media else state.request.path)

        if state.error:
            self._state.setText("Erreur")
            self._state.set_kind("erreur")
        elif state.paused:
            self._state.setText("En pause")
            self._state.set_kind("alerte")
        else:
            self._state.setText("En lecture")
            self._state.set_kind("succes")

        if media and media.thumbnail:
            pixmap = QPixmap(media.thumbnail)
            if not pixmap.isNull():
                self._thumb.setPixmap(
                    pixmap.scaled(132, 76, Qt.KeepAspectRatioByExpanding,
                                  Qt.SmoothTransformation)
                )
                self._thumb.setText("")
                return
        self._thumb.setPixmap(QPixmap())
        self._thumb.setText(state.request.kind.label)


class HomeView(QWidget):
    """Page d'accueil."""

    navigate = Signal(str)
    notify = Signal(str, str)

    def __init__(self, engine, repos, scheduler, settings, parent=None):
        super().__init__(parent)
        self._engine = engine
        self._repos = repos
        self._scheduler = scheduler
        self._settings = settings
        self._tiles = []
        self._build()

        # 4 s suffisent pour un tableau de bord : l'heure de la prochaine
        # transition n'a pas besoin d'etre rafraichie deux fois par seconde.
        self._tick = QTimer(self)
        self._tick.setInterval(4000)
        self._tick.timeout.connect(self._on_tick)
        self._tick.start()
        self.refresh()

    def set_updates_active(self, active: bool) -> None:
        """Arrete le minuteur quand la page n'est plus visible."""
        if active and not self._tick.isActive():
            self._tick.start()
            self.refresh()
        elif not active and self._tick.isActive():
            self._tick.stop()

    def _on_tick(self) -> None:
        # Une page masquee par un autre onglet n'a rien a redessiner.
        if self.isVisible():
            self.refresh()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(14)

        header = QHBoxLayout()
        box = QVBoxLayout()
        title = QLabel(APP_NAME)
        title.setObjectName("pageTitle")
        box.addWidget(title)
        subtitle = QLabel(f"Version {APP_VERSION} - fonds d'ecran animes pour Windows")
        subtitle.setObjectName("pageSubtitle")
        box.addWidget(subtitle)
        header.addLayout(box)
        header.addStretch(1)
        root.addLayout(header)

        # --- Avertissements ---
        self._warning = QLabel()
        self._warning.setWordWrap(True)
        self._warning.setObjectName("card")
        self._warning.setStyleSheet(
            "padding:12px;border-left:4px solid #e8a33d;border-radius:9px;"
        )
        self._warning.hide()
        root.addWidget(self._warning)

        # --- Fonds actifs ---
        root.addWidget(section_title("Fonds d'ecran actifs"))
        self._active_box = QVBoxLayout()
        self._active_box.setSpacing(8)
        root.addLayout(self._active_box)

        # --- Etat, en tuiles ---
        root.addWidget(section_title("Etat"))
        tuiles = QGridLayout()
        tuiles.setSpacing(10)
        self._status_labels = {}
        for index, (key, label) in enumerate(
            [
                ("planif", "Planification"),
                ("prochain", "Prochaine transition"),
                ("bibliotheque", "Bibliotheque"),
                ("regles", "Regles horaires"),
                ("couche", "Couche de bureau"),
                ("moteur", "Lecteur video"),
            ]
        ):
            tuile, interieur = card()
            interieur.setContentsMargins(14, 12, 14, 12)
            interieur.setSpacing(3)

            value = QLabel("-")
            value.setWordWrap(True)
            value.setStyleSheet("font-size:15px;font-weight:600;")
            interieur.addWidget(value)

            caption = QLabel(label)
            caption.setObjectName("hint")
            interieur.addWidget(caption)
            interieur.addStretch(1)

            tuile.setMinimumHeight(74)
            tuiles.addWidget(tuile, index // 3, index % 3)
            self._status_labels[key] = value
        for colonne in range(3):
            tuiles.setColumnStretch(colonne, 1)
        root.addLayout(tuiles)

        # --- Acces rapides ---
        root.addWidget(section_title("Acces rapides"))
        quick = QHBoxLayout()
        quick.setSpacing(8)
        for label, page, icon_name in (
            ("Bibliotheque", "library", "bibliotheque"),
            ("Ecrans", "monitors", "ecrans"),
            ("Horaires", "scheduler", "horaires"),
            ("Editeur", "editor", "editeur"),
            ("Performances", "performance", "performances"),
        ):
            button = QPushButton(f"  {label}")
            button.setIcon(icon(icon_name))
            button.clicked.connect(lambda _=False, p=page: self.navigate.emit(p))
            quick.addWidget(button)
        quick.addStretch(1)
        root.addLayout(quick)
        root.addStretch(1)

    def refresh(self) -> None:
        monitors = self._engine.monitor_manager.monitors

        # Ajuste le nombre de tuiles au nombre d'ecrans.
        while len(self._tiles) < len(monitors):
            tile = ActiveWallpaperTile()
            self._tiles.append(tile)
            self._active_box.addWidget(tile)
        while len(self._tiles) > len(monitors):
            tile = self._tiles.pop()
            self._active_box.removeWidget(tile)
            tile.deleteLater()

        for tile, monitor in zip(self._tiles, monitors):
            state = self._engine.state_for(monitor.key)
            media = None
            if state and state.request:
                media = self._repos.media.get_by_path(state.request.path)
            tile.update_state(monitor, state, media)

        labels = self._status_labels
        labels["planif"].setText(
            "Active" if self._scheduler.is_active
            else ("Suspendue" if self._scheduler.is_suspended else "Desactivee")
        )
        labels["prochain"].setText(self._scheduler.describe_next())
        labels["bibliotheque"].setText(
            f"{self._repos.media.count()} fond(s), "
            f"{self._repos.media.count_missing()} introuvable(s)"
        )
        labels["regles"].setText(
            f"{self._repos.schedule.count(enabled_only=True)} active(s) "
            f"sur {self._repos.schedule.count()}"
        )

        host = self._engine.host
        if host is None:
            labels["couche"].setText("Non initialisee")
        else:
            modes = {
                wd.LAYOUT_SIBLING: "WorkerW (agencement Windows 10)",
                wd.LAYOUT_PROGMAN_CHILD: "WorkerW (agencement Windows 11)",
                wd.LAYOUT_DEFVIEW_OVERLAY: "Couche des icones (Windows 11 recent)",
                wd.LAYOUT_PROGMAN_FALLBACK: "Progman (mode de repli)",
            }
            labels["couche"].setText(modes.get(host.layout, host.layout))

        from ..engine.backends import vlc_runtime

        version = vlc_runtime.ensure_loaded()
        labels["moteur"].setText(
            f"libVLC {version}" if version else "libVLC absente (videos indisponibles)"
        )

        self._refresh_warning()

    def _refresh_warning(self) -> None:
        messages = []
        rivals = wd.detect_rival_wallpaper_apps()
        if rivals:
            messages.append(
                f"<b>{', '.join(rivals)}</b> occupe egalement la couche de fond "
                "d'ecran de Windows. Les deux rendus se superposent : fermez "
                "l'autre logiciel pour voir vos fonds Wallpaper Studio."
            )
        host = self._engine.host
        if host is not None and host.hides_desktop_icons:
            messages.append(
                "Sur cette version de Windows, le bureau est dessine par "
                "DirectComposition : le fond d'ecran doit etre place dans la "
                "couche des icones et <b>les recouvre</b> tant qu'il est "
                "actif. Aucune autre couche n'est composee par le systeme."
            )
        if host is not None and host.is_fallback:
            messages.append(
                "Windows n'a pas fourni de couche <i>WorkerW</i> : le rendu "
                "utilise Progman, ce qui peut faire scintiller les icones."
            )
        missing = self._repos.media.count_missing()
        if missing:
            messages.append(
                f"{missing} fichier(s) de la bibliotheque sont introuvables."
            )

        if messages:
            self._warning.setText("<br><br>".join(messages))
            self._warning.show()
        else:
            self._warning.hide()
