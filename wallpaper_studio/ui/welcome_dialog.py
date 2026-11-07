"""Choix de la langue au tout premier lancement.

Le dialogue est volontairement bilingue : l'utilisateur ne connait pas encore
la langue de l'application, il faut donc que les deux options lui parlent.
"""

from __future__ import annotations

import logging
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .. import APP_NAME, APP_VERSION
from ..i18n import available_languages
from .theme import app_icon, palette_for, stylesheet

log = logging.getLogger(__name__)

#: Langues proposees au premier lancement : code, libelle, drapeau, accroche.
CHOIX = [
    ("fr", "Français", "🇫🇷", "Interface en français"),
    ("en", "English", "🇬🇧", "English interface"),
]


class LanguageButton(QPushButton):
    """Grande tuile cliquable pour une langue."""

    def __init__(self, drapeau: str, libelle: str, accroche: str, parent=None):
        super().__init__(parent)
        couleurs = palette_for("sombre")
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(210, 132)
        self.setObjectName("langueTuile")
        self.setStyleSheet(
            f"QPushButton#langueTuile{{background:{couleurs.surface};"
            f"border:1px solid {couleurs.bordure};border-radius:14px;}}"
            f"QPushButton#langueTuile:hover{{border-color:{couleurs.accent};"
            f"background:{couleurs.surface_haut};}}"
            f"QPushButton#langueTuile:checked{{border:2px solid {couleurs.accent};"
            f"background:{couleurs.surface_haut};}}"
        )

        corps = QVBoxLayout(self)
        corps.setContentsMargins(14, 16, 14, 16)
        corps.setSpacing(5)

        emoji = QLabel(drapeau)
        emoji.setAlignment(Qt.AlignCenter)
        emoji.setStyleSheet("font-size:34px;")
        corps.addWidget(emoji)

        nom = QLabel(libelle)
        nom.setAlignment(Qt.AlignCenter)
        nom.setStyleSheet("font-size:16px;font-weight:600;")
        corps.addWidget(nom)

        detail = QLabel(accroche)
        detail.setAlignment(Qt.AlignCenter)
        detail.setStyleSheet(f"color:{couleurs.texte_doux};font-size:11px;")
        corps.addWidget(detail)


class WelcomeDialog(QDialog):
    """Demande la langue de l'interface au premier demarrage."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._code = "fr"
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(app_icon(64))
        self.setStyleSheet(stylesheet("sombre"))
        self.setModal(True)
        self.setFixedWidth(520)
        self._build()

    def _build(self) -> None:
        couleurs = palette_for("sombre")
        racine = QVBoxLayout(self)
        racine.setContentsMargins(30, 26, 30, 24)
        racine.setSpacing(6)

        logo = QLabel()
        logo.setPixmap(app_icon(72).pixmap(72, 72))
        logo.setAlignment(Qt.AlignCenter)
        racine.addWidget(logo)

        titre = QLabel(APP_NAME)
        titre.setAlignment(Qt.AlignCenter)
        titre.setStyleSheet("font-size:24px;font-weight:700;margin-top:10px;")
        racine.addWidget(titre)

        version = QLabel(f"Version {APP_VERSION}")
        version.setAlignment(Qt.AlignCenter)
        version.setStyleSheet(f"color:{couleurs.texte_doux};font-size:12px;")
        racine.addWidget(version)

        invite = QLabel("Choisissez votre langue  ·  Choose your language")
        invite.setAlignment(Qt.AlignCenter)
        invite.setStyleSheet("font-size:14px;font-weight:600;margin-top:18px;")
        racine.addWidget(invite)

        tuiles = QHBoxLayout()
        tuiles.setSpacing(14)
        tuiles.addStretch(1)
        self._boutons = {}
        disponibles = {code for code, _ in available_languages()}
        for code, libelle, drapeau, accroche in CHOIX:
            if code != "fr" and code not in disponibles:
                continue
            bouton = LanguageButton(drapeau, libelle, accroche)
            bouton.clicked.connect(lambda _=False, c=code: self._choisir(c))
            tuiles.addWidget(bouton)
            self._boutons[code] = bouton
        tuiles.addStretch(1)
        racine.addSpacing(10)
        racine.addLayout(tuiles)

        note = QLabel(
            "Vous pourrez en changer a tout moment dans les parametres.\n"
            "You can change this at any time in the settings."
        )
        note.setAlignment(Qt.AlignCenter)
        note.setStyleSheet(f"color:{couleurs.texte_doux};font-size:11px;")
        racine.addSpacing(14)
        racine.addWidget(note)

        self._valider = QPushButton("Continuer  ·  Continue")
        self._valider.setObjectName("primary")
        self._valider.setFixedHeight(40)
        self._valider.clicked.connect(self.accept)
        racine.addSpacing(16)
        racine.addWidget(self._valider)

        self._choisir("fr")

    def _choisir(self, code: str) -> None:
        self._code = code
        for autre, bouton in self._boutons.items():
            bouton.setChecked(autre == code)

    def language(self) -> str:
        """Code de la langue retenue."""
        return self._code


def ask_language_if_needed(settings) -> Optional[str]:
    """Affiche le dialogue si la langue n'a jamais ete choisie.

    Retourne le code retenu, ou ``None`` si la question n'avait pas lieu
    d'etre. Le reglage ``langue_choisie`` sert de temoin : il distingue une
    langue choisie par l'utilisateur de la valeur par defaut.
    """
    if settings.get("langue_choisie", False):
        return None

    dialogue = WelcomeDialog()
    dialogue.exec()
    code = dialogue.language()
    settings.update({"langue": code, "langue_choisie": True})
    log.info("Langue choisie au premier lancement : %s", code)
    return code
