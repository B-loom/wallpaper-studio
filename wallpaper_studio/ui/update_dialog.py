"""Interface de mise a jour : notification, telechargement, installation.

Le parcours est volontairement en trois temps, chacun demandant l'accord de
l'utilisateur :

1. une version est disponible -> « Telecharger » ou « Plus tard » ;
2. le telechargement progresse -> « Annuler » reste possible a tout moment ;
3. le fichier est pret -> « Redemarrer et installer » ou « Annuler ».

Rien n'est installe sans ce dernier clic.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from .. import APP_NAME, APP_VERSION
from ..i18n import tr
from ..system import updater
from ..system.updater import Release
from .theme import app_icon, palette_for, stylesheet

log = logging.getLogger(__name__)


class UpdateChecker(QThread):
    """Interroge GitHub sans bloquer l'interface."""

    fini = Signal(object, object)   # Release | None, message d'erreur | None

    def run(self) -> None:
        release, erreur = updater.check_for_update()
        self.fini.emit(release, erreur)


class DownloadWorker(QThread):
    """Telecharge le fichier de mise a jour."""

    progression = Signal(int, int)
    fini = Signal(object, object)   # Path | None, erreur | None

    def __init__(self, release: Release, parent=None):
        super().__init__(parent)
        self._release = release
        self._annule = False

    def annuler(self) -> None:
        self._annule = True

    def run(self) -> None:
        chemin, erreur = updater.download_release(
            self._release,
            on_progress=lambda recu, total: self.progression.emit(recu, total),
            annule=lambda: self._annule,
        )
        self.fini.emit(chemin, erreur)


class UpdateDialog(QDialog):
    """Propose, telecharge puis installe une mise a jour."""

    #: Emis quand l'utilisateur demande le redemarrage pour installer.
    install_requested = Signal(object)   # Path du fichier telecharge

    def __init__(self, release: Release, parent: Optional[QWidget] = None,
                 theme: str = "sombre"):
        super().__init__(parent)
        self._release = release
        self._fichier: Optional[Path] = None
        self._worker: Optional[DownloadWorker] = None

        self.setWindowTitle(tr("Une mise a jour est disponible"))
        self.setWindowIcon(app_icon(64))
        self.setStyleSheet(stylesheet(theme))
        self.setMinimumWidth(540)
        self._build(theme)

    def _build(self, theme: str) -> None:
        couleurs = palette_for(theme)
        racine = QVBoxLayout(self)
        racine.setContentsMargins(24, 22, 24, 20)
        racine.setSpacing(12)

        entete = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(app_icon(52).pixmap(52, 52))
        entete.addWidget(logo)

        textes = QVBoxLayout()
        textes.setSpacing(2)
        titre = QLabel(tr("Une mise a jour est disponible"))
        titre.setStyleSheet("font-size:18px;font-weight:700;")
        textes.addWidget(titre)
        sous = QLabel(f"{APP_NAME}  {APP_VERSION}  →  {self._release.version}")
        sous.setStyleSheet(f"color:{couleurs.texte_doux};font-size:12px;")
        textes.addWidget(sous)
        entete.addLayout(textes, 1)
        racine.addLayout(entete)

        if self._release.notes.strip():
            notes = QTextBrowser()
            notes.setMarkdown(self._release.notes)
            notes.setOpenExternalLinks(False)
            notes.setOpenLinks(False)
            notes.setMaximumHeight(220)
            racine.addWidget(notes)

        self._etat = QLabel("")
        self._etat.setObjectName("hint")
        self._etat.setWordWrap(True)
        racine.addWidget(self._etat)

        self._barre = QProgressBar()
        self._barre.hide()
        racine.addWidget(self._barre)

        actions = QHBoxLayout()
        actions.addStretch(1)

        self._plus_tard = QPushButton(tr("Plus tard"))
        self._plus_tard.clicked.connect(self.reject)
        actions.addWidget(self._plus_tard)

        self._action = QPushButton(tr("Telecharger"))
        self._action.setObjectName("primary")
        self._action.clicked.connect(self._telecharger)
        actions.addWidget(self._action)
        racine.addLayout(actions)

        if not self._release.telechargeable:
            self._etat.setText(
                "Cette version ne propose pas de fichier a telecharger. "
                "Rendez-vous sur la page de publication."
            )
            self._action.setEnabled(False)

    # --- Telechargement ----------------------------------------------------
    def _telecharger(self) -> None:
        if self._fichier is not None:
            self._installer()
            return

        self._action.setEnabled(False)
        self._plus_tard.setText(tr("Annuler"))
        self._barre.setRange(0, 100)
        self._barre.setValue(0)
        self._barre.show()
        self._etat.setText(tr("Telechargement en cours..."))

        self._worker = DownloadWorker(self._release, self)
        self._worker.progression.connect(self._on_progress)
        self._worker.fini.connect(self._on_downloaded)
        self._worker.start()

    def _on_progress(self, recu: int, total: int) -> None:
        if total > 0:
            self._barre.setRange(0, 100)
            self._barre.setValue(int(recu * 100 / total))
            self._etat.setText(
                f"{tr('Telechargement en cours...')}  "
                f"{recu / 1048576:.1f} / {total / 1048576:.1f} Mo"
            )
        else:
            self._barre.setRange(0, 0)

    def _on_downloaded(self, chemin, erreur) -> None:
        self._barre.hide()
        self._plus_tard.setText(tr("Plus tard"))
        self._action.setEnabled(True)

        if erreur:
            self._etat.setText(f"<b>{erreur}</b>")
            self._action.setText(tr("Telecharger"))
            return
        if chemin is None:
            # Annulation demandee par l'utilisateur.
            self._etat.setText("")
            self._action.setText(tr("Telecharger"))
            return

        self._fichier = Path(chemin)
        updater.cleanup_downloads(garder=self._fichier)
        self._etat.setText(
            f"{tr('Mise a jour prete')} : {self._fichier.name}"
        )
        self._action.setText(tr("Redemarrer et installer"))

    # --- Installation ------------------------------------------------------
    def _installer(self) -> None:
        if self._fichier is None:
            return
        log.info("Installation demandee : %s", self._fichier)
        self.install_requested.emit(self._fichier)
        self.accept()

    def reject(self) -> None:  # noqa: D102 - API Qt
        if self._worker is not None and self._worker.isRunning():
            self._worker.annuler()
            self._worker.wait(3000)
            self._etat.setText("")
            self._barre.hide()
            self._action.setEnabled(True)
            self._action.setText(tr("Telecharger"))
            self._plus_tard.setText(tr("Plus tard"))
            return
        super().reject()


def apply_update(fichier: Path) -> bool:
    """Lance l'installateur telecharge, puis rend la main pour quitter.

    Retourne vrai si le processus a bien ete demarre. L'appelant doit ensuite
    fermer l'application pour que l'installation puisse remplacer les fichiers.
    """
    fichier = Path(fichier)
    if not fichier.exists():
        log.error("Fichier de mise a jour introuvable : %s", fichier)
        return False

    try:
        if fichier.suffix.lower() in (".exe", ".msi"):
            if fichier.suffix.lower() == ".msi":
                subprocess.Popen(["msiexec", "/i", str(fichier)], close_fds=True)
            else:
                subprocess.Popen([str(fichier)], close_fds=True)
        else:
            # Archive : on ouvre simplement le dossier, l'utilisateur decide.
            subprocess.Popen(["explorer", "/select,", str(fichier)])
            return True
    except OSError as exc:
        log.error("Lancement de l'installateur impossible : %s", exc)
        return False

    log.info("Installateur lance, fermeture de l'application")
    return True
