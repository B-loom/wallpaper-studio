"""Page Nouveautes : notes de version et recherche de mise a jour.

Le texte affiche suit la langue de l'interface : les notes sont stockees dans
``resources/changelog/<code>.md``. Si la langue active n'a pas de fichier, le
francais sert de repli plutot que de laisser la page vide.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from .. import APP_NAME, APP_VERSION
from ..app_paths import resource_dir
from ..i18n import current_language, tr
from .theme import icon, palette_for
from .widgets.common import Badge

log = logging.getLogger(__name__)


def changelog_path(code: Optional[str] = None) -> Optional[Path]:
    """Fichier de notes pour une langue, avec repli sur le francais."""
    dossier = resource_dir() / "changelog"
    for essai in (code or current_language(), "fr"):
        chemin = dossier / f"{essai}.md"
        if chemin.exists():
            return chemin
    return None


def changelog_text(code: Optional[str] = None) -> str:
    chemin = changelog_path(code)
    if chemin is None:
        return tr("Notes de version indisponibles.")
    try:
        return chemin.read_text(encoding="utf-8")
    except OSError as exc:
        log.warning("Notes de version illisibles : %s", exc)
        return tr("Notes de version indisponibles.")


class ChangelogView(QWidget):
    """Page Nouveautes."""

    notify = Signal(str, str)
    #: Demande une recherche de mise a jour declenchee par l'utilisateur.
    check_requested = Signal()

    def __init__(self, settings, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._settings = settings
        self._build()
        self.refresh()

    def _build(self) -> None:
        couleurs = palette_for(self._settings.get("theme", "sombre"))
        racine = QVBoxLayout(self)
        racine.setContentsMargins(24, 20, 24, 20)
        racine.setSpacing(12)

        entete = QHBoxLayout()
        titre = QLabel(tr("Nouveautes"))
        titre.setObjectName("pageTitle")
        entete.addWidget(titre)
        entete.addStretch(1)

        self._version = Badge(f"{APP_NAME} {APP_VERSION}", "neutre")
        entete.addWidget(self._version)

        self._bouton = QPushButton("  " + tr("Rechercher les mises a jour"))
        self._bouton.setIcon(icon("importer"))
        self._bouton.setObjectName("primary")
        self._bouton.clicked.connect(self._demander)
        entete.addWidget(self._bouton)
        racine.addLayout(entete)

        self._etat = QLabel("")
        self._etat.setObjectName("hint")
        self._etat.setWordWrap(True)
        racine.addWidget(self._etat)

        self._texte = QTextBrowser()
        self._texte.setOpenExternalLinks(False)
        self._texte.setOpenLinks(False)
        self._texte.setStyleSheet(
            f"QTextBrowser{{background:{couleurs.surface};"
            f"border:1px solid {couleurs.bordure};border-radius:14px;"
            f"padding:16px;}}"
        )
        racine.addWidget(self._texte, 1)

    def refresh(self) -> None:
        """Recharge les notes dans la langue active."""
        self._texte.setMarkdown(changelog_text())
        self._version.setText(f"{APP_NAME} {APP_VERSION}")

    # --- Recherche de mise a jour ------------------------------------------
    def _demander(self) -> None:
        self._bouton.setEnabled(False)
        self._etat.setText(tr("Rechercher les mises a jour") + "...")
        self.check_requested.emit()

    def set_check_result(self, message: str) -> None:
        """Affiche le resultat d'une recherche de mise a jour."""
        self._bouton.setEnabled(True)
        self._etat.setText(message)
