"""Traduction de l'interface par parcours de l'arbre de widgets.

Pourquoi cette approche
-----------------------
Les textes de l'interface sont ecrits en francais directement dans le code des
vues. Les envelopper un par un dans un appel de traduction aurait demande de
modifier plusieurs centaines d'endroits, avec autant d'occasions de casser une
vue. On procede autrement : une fois une page construite, on parcourt ses
widgets et on remplace chaque texte par sa traduction, en s'appuyant sur le
catalogue (voir :mod:`wallpaper_studio.i18n`).

Le francais etant la langue source, ce parcours ne fait **rien** quand la
langue active est le francais : aucun cout, aucun risque.

Limite assumee
--------------
Les messages composes a l'execution (``f"{n} fond(s) affiche(s)"``) ne peuvent
pas etre retrouves dans le catalogue : ils restent en francais. Les libelles
fixes, c'est-a-dire l'essentiel de l'interface, sont bien traduits.
"""

from __future__ import annotations

import logging
from typing import Optional

from PySide6.QtWidgets import (
    QAbstractButton,
    QAbstractSpinBox,
    QComboBox,
    QGroupBox,
    QLabel,
    QLineEdit,
    QTableWidget,
    QTabWidget,
    QWidget,
)

from ..i18n import current_language, has_translation, tr

log = logging.getLogger(__name__)

#: Propriete posee sur un widget deja traduit, pour ne pas le retraiter.
_MARQUEUR = "_ws_langue"


def _traduire(texte: Optional[str]) -> Optional[str]:
    """Traduit un libelle, ou retourne ``None`` s'il n'y a rien a changer."""
    if not texte or not texte.strip():
        return None
    # Les libelles portent parfois des espaces de mise en forme ("  Importer").
    noyau = texte.strip()
    if not has_translation(noyau):
        return None
    traduit = tr(noyau)
    if traduit == noyau:
        return None
    return texte.replace(noyau, traduit)


def translate_widget(widget: QWidget) -> None:
    """Traduit un widget isole, sans ses enfants."""
    # Libelles et boutons
    if isinstance(widget, (QLabel, QAbstractButton)):
        nouveau = _traduire(widget.text())
        if nouveau is not None:
            widget.setText(nouveau)
    if isinstance(widget, QGroupBox):
        nouveau = _traduire(widget.title())
        if nouveau is not None:
            widget.setTitle(nouveau)
    if isinstance(widget, QLineEdit):
        nouveau = _traduire(widget.placeholderText())
        if nouveau is not None:
            widget.setPlaceholderText(nouveau)
    if isinstance(widget, QComboBox):
        for index in range(widget.count()):
            nouveau = _traduire(widget.itemText(index))
            if nouveau is not None:
                widget.setItemText(index, nouveau)
    if isinstance(widget, QTabWidget):
        for index in range(widget.count()):
            nouveau = _traduire(widget.tabText(index))
            if nouveau is not None:
                widget.setTabText(index, nouveau)
    if isinstance(widget, QAbstractSpinBox):
        # Les suffixes (« images/s », « % ») sont des libelles a part entiere.
        for lire, ecrire in (("suffix", "setSuffix"), ("prefix", "setPrefix"),
                             ("specialValueText", "setSpecialValueText")):
            accesseur = getattr(widget, lire, None)
            if accesseur is None:
                continue
            nouveau = _traduire(accesseur())
            if nouveau is not None:
                getattr(widget, ecrire)(nouveau)
    if isinstance(widget, QTableWidget):
        for colonne in range(widget.columnCount()):
            entete = widget.horizontalHeaderItem(colonne)
            if entete is not None:
                nouveau = _traduire(entete.text())
                if nouveau is not None:
                    entete.setText(nouveau)

    # Infobulles, communes a tous les widgets
    nouveau = _traduire(widget.toolTip())
    if nouveau is not None:
        widget.setToolTip(nouveau)

    # Actions (menus contextuels poses sur le widget)
    for action in widget.actions():
        nouveau = _traduire(action.text())
        if nouveau is not None:
            action.setText(nouveau)


def translate_tree(racine: Optional[QWidget]) -> int:
    """Traduit un widget et toute sa descendance. Retourne le nombre traite.

    Sans effet si la langue active est la langue source.
    """
    if racine is None or current_language() == "fr":
        return 0

    langue = current_language()
    if racine.property(_MARQUEUR) == langue:
        return 0

    compte = 0
    for widget in [racine] + racine.findChildren(QWidget):
        try:
            translate_widget(widget)
            compte += 1
        except RuntimeError:
            # Widget detruit entre-temps : sans importance.
            continue
    racine.setProperty(_MARQUEUR, langue)
    log.debug("Interface traduite : %s widgets en %s", compte, langue)
    return compte
