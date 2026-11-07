"""Identite graphique : palette, feuille de style et icones vectorielles.

Le theme sombre est le defaut. Les couleurs sont definies une seule fois ici et
injectees dans la feuille de style, ce qui permet d'ajouter un theme clair sans
toucher aux vues.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

from PySide6.QtCore import QByteArray, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer


@dataclass(frozen=True)
class Palette:
    """Couleurs du theme.

    L'identite visuelle est une nuit etoilee : des fonds bleu nuit tres
    sombres, et un accent qui glisse du violet au cyan comme une nebuleuse.
    """

    nom: str
    fond: str              # fond de la fenetre
    fond_alt: str          # panneaux lateraux
    surface: str           # cartes, champs
    surface_haut: str      # survol
    bordure: str
    bordure_claire: str    # separateurs discrets
    texte: str
    texte_doux: str
    accent: str
    accent_clair: str
    accent_sombre: str
    accent2: str           # seconde couleur des degrades
    succes: str
    alerte: str
    erreur: str

    def as_dict(self) -> Dict[str, str]:
        return {k: v for k, v in self.__dict__.items() if k != "nom"}


SOMBRE = Palette(
    nom="sombre",
    fond="#0a0b14",
    fond_alt="#0e1020",
    surface="#161a2e",
    surface_haut="#1e2440",
    bordure="#272e4d",
    bordure_claire="#1b2138",
    texte="#eef0fb",
    texte_doux="#8b93b8",
    accent="#7c5cff",
    accent_clair="#9d85ff",
    accent_sombre="#5b3fd4",
    accent2="#22d3ee",
    succes="#34d399",
    alerte="#fbbf24",
    erreur="#fb7185",
)

CLAIR = Palette(
    nom="clair",
    fond="#f6f7fc",
    fond_alt="#eef0f8",
    surface="#ffffff",
    surface_haut="#e9ecf7",
    bordure="#d6dae9",
    bordure_claire="#e6e9f3",
    texte="#141829",
    texte_doux="#5a6180",
    accent="#6436e0",
    accent_clair="#7f55f0",
    accent_sombre="#4a21b8",
    accent2="#0891b2",
    succes="#059669",
    alerte="#b45309",
    erreur="#dc2626",
)

THEMES = {"sombre": SOMBRE, "clair": CLAIR}


def palette_for(name: str) -> Palette:
    return THEMES.get(name, SOMBRE)


# --- Feuille de style -------------------------------------------------------
_STYLESHEET = """
* {{
    font-family: "Segoe UI Variable Display", "Segoe UI", "Inter", sans-serif;
    font-size: 13px;
}}
QWidget {{
    background-color: {fond};
    color: {texte};
}}
QMainWindow, QDialog {{ background-color: {fond}; }}
QLabel, QCheckBox, QRadioButton {{ background: transparent; }}

/* --- Barre laterale --- */
#sidebar {{
    background-color: {fond_alt};
    border: none;
    border-right: 1px solid {bordure_claire};
}}
#appTitle {{
    font-size: 17px;
    font-weight: 700;
    color: {texte};
    padding: 22px 18px 2px 18px;
}}
#appSubtitle {{
    font-size: 11px;
    color: {texte_doux};
    padding: 0 18px 18px 18px;
}}
QPushButton#navButton {{
    background: transparent;
    border: none;
    border-radius: 10px;
    color: {texte_doux};
    padding: 11px 14px;
    margin: 1px 0;
    text-align: left;
    font-size: 13px;
    font-weight: 500;
}}
QPushButton#navButton:hover {{
    background-color: {surface};
    color: {texte};
}}
QPushButton#navButton:checked {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {accent}, stop:1 {accent_sombre});
    color: #ffffff;
    font-weight: 600;
}}

/* --- Titres --- */
#pageTitle {{ font-size: 25px; font-weight: 700; }}
#pageSubtitle {{ font-size: 12px; color: {texte_doux}; }}
#sectionTitle {{
    font-size: 11px; font-weight: 700; color: {texte_doux};
    text-transform: uppercase; letter-spacing: 1px; margin-top: 8px;
}}
#hint {{ color: {texte_doux}; font-size: 12px; }}

/* --- Cartes --- */
#card, QGroupBox {{
    background-color: {surface};
    border: 1px solid {bordure};
    border-radius: 14px;
}}
QGroupBox {{
    margin-top: 18px;
    padding: 20px 16px 16px 16px;
    font-weight: 600;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 14px;
    padding: 0 7px;
    color: {texte_doux};
    font-size: 11px;
    letter-spacing: 1px;
}}
#mediaCard {{
    background-color: {surface};
    border: 1px solid {bordure};
    border-radius: 12px;
}}
#mediaCard:hover {{ border-color: {accent}; background-color: {surface_haut}; }}
#mediaCard[selected="true"] {{
    border: 2px solid {accent};
    background-color: {surface_haut};
}}

/* --- Boutons --- */
QPushButton {{
    background-color: {surface_haut};
    border: 1px solid {bordure};
    border-radius: 9px;
    padding: 9px 16px;
    color: {texte};
    font-weight: 500;
}}
QPushButton:hover {{ background-color: {bordure}; border-color: {accent_sombre}; }}
QPushButton:pressed {{ background-color: {surface}; }}
QPushButton:disabled {{
    color: {texte_doux}; background-color: {surface};
    border-color: {bordure_claire};
}}
QPushButton#primary {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {accent}, stop:1 {accent2});
    border: none;
    color: #ffffff;
    font-weight: 600;
    padding: 10px 20px;
}}
QPushButton#primary:hover {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {accent_clair}, stop:1 {accent2});
}}
QPushButton#primary:pressed {{ background: {accent_sombre}; }}
QPushButton#danger {{
    background-color: {erreur}; border-color: {erreur}; color: #ffffff;
}}
QPushButton#ghost {{ background: transparent; border: none; color: {texte_doux}; }}
QPushButton#ghost:hover {{ color: {accent_clair}; background: {surface_haut}; }}

/* --- Champs --- */
QLineEdit, QComboBox, QSpinBox, QTimeEdit, QDoubleSpinBox, QPlainTextEdit, QTextEdit {{
    background-color: {fond_alt};
    border: 1px solid {bordure};
    border-radius: 9px;
    padding: 8px 11px;
    color: {texte};
    selection-background-color: {accent};
}}
QLineEdit:hover, QComboBox:hover {{ border-color: {accent_sombre}; }}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QTimeEdit:focus, QDoubleSpinBox:focus {{
    border-color: {accent};
    background-color: {surface};
}}
QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox QAbstractItemView {{
    background-color: {surface};
    border: 1px solid {bordure};
    border-radius: 9px;
    selection-background-color: {accent};
    outline: none;
    padding: 4px;
}}

/* --- Curseurs --- */
QSlider::groove:horizontal {{ height: 5px; background: {bordure}; border-radius: 3px; }}
QSlider::sub-page:horizontal {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {accent}, stop:1 {accent2});
    border-radius: 3px;
}}
QSlider::handle:horizontal {{
    background: #ffffff; width: 15px; height: 15px;
    margin: -6px 0; border-radius: 8px;
}}
QSlider::handle:horizontal:hover {{ background: {accent_clair}; }}

/* --- Cases a cocher --- */
QCheckBox, QRadioButton {{ spacing: 9px; }}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 18px; height: 18px;
    border: 1px solid {bordure};
    border-radius: 5px;
    background: {fond_alt};
}}
QRadioButton::indicator {{ border-radius: 10px; }}
QCheckBox::indicator:hover, QRadioButton::indicator:hover {{ border-color: {accent}; }}
QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
    background: {accent}; border-color: {accent};
}}

/* --- Listes et tableaux --- */
QListWidget, QTreeWidget, QTableWidget {{
    background-color: {surface};
    border: 1px solid {bordure};
    border-radius: 12px;
    outline: none;
    gridline-color: {bordure_claire};
}}
QListWidget::item, QTreeWidget::item {{ padding: 8px; border-radius: 7px; }}
QTableWidget::item {{ padding: 7px 6px; }}
QListWidget::item:selected, QTreeWidget::item:selected, QTableWidget::item:selected {{
    background-color: {accent}; color: #ffffff;
}}
QListWidget::item:hover, QTreeWidget::item:hover {{ background-color: {surface_haut}; }}
QHeaderView::section {{
    background-color: {fond_alt};
    color: {texte_doux};
    border: none;
    border-bottom: 1px solid {bordure};
    padding: 10px 8px;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.6px;
}}

/* --- Onglets --- */
QTabWidget::pane {{ border: 1px solid {bordure}; border-radius: 12px; top: -1px; }}
QTabBar::tab {{
    background: transparent; color: {texte_doux};
    padding: 10px 18px; border-radius: 9px; margin-right: 4px;
}}
QTabBar::tab:selected {{ background: {surface}; color: {texte}; font-weight: 600; }}
QTabBar::tab:hover {{ color: {texte}; }}

/* --- Barres de defilement --- */
QScrollBar:vertical {{ background: transparent; width: 11px; margin: 2px; }}
QScrollBar::handle:vertical {{
    background: {bordure}; border-radius: 5px; min-height: 34px;
}}
QScrollBar::handle:vertical:hover {{ background: {accent_sombre}; }}
QScrollBar:horizontal {{ background: transparent; height: 11px; margin: 2px; }}
QScrollBar::handle:horizontal {{
    background: {bordure}; border-radius: 5px; min-width: 34px;
}}
QScrollBar::handle:horizontal:hover {{ background: {accent_sombre}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QScrollArea {{ border: none; background: transparent; }}

/* --- Progression --- */
QProgressBar {{
    background: {fond_alt}; border: 1px solid {bordure};
    border-radius: 8px; height: 16px; text-align: center; color: {texte};
    font-size: 11px;
}}
QProgressBar::chunk {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {accent}, stop:1 {accent2});
    border-radius: 7px;
}}

/* --- Divers --- */
QToolTip {{
    background-color: {surface_haut}; color: {texte};
    border: 1px solid {bordure}; border-radius: 8px; padding: 7px;
}}
QMenu {{
    background-color: {surface}; border: 1px solid {bordure};
    border-radius: 10px; padding: 6px;
}}
QMenu::item {{ padding: 8px 26px 8px 14px; border-radius: 7px; }}
QMenu::item:selected {{ background-color: {accent}; color: #ffffff; }}
QMenu::separator {{ height: 1px; background: {bordure}; margin: 5px 8px; }}
QSplitter::handle {{ background: {bordure}; }}
#statusBadge {{
    background-color: {surface_haut}; border: 1px solid {bordure};
    border-radius: 11px; padding: 4px 12px; color: {texte_doux}; font-size: 11px;
}}
#badgeSucces {{ background-color: {succes}; color: #04140d; border: none;
    border-radius: 11px; padding: 4px 12px; font-size: 11px; font-weight: 700; }}
#badgeAlerte {{ background-color: {alerte}; color: #1d1304; border: none;
    border-radius: 11px; padding: 4px 12px; font-size: 11px; font-weight: 700; }}
#badgeErreur {{ background-color: {erreur}; color: #2a0409; border: none;
    border-radius: 11px; padding: 4px 12px; font-size: 11px; font-weight: 700; }}
"""


def stylesheet(theme: str = "sombre") -> str:
    """Feuille de style complete pour le theme demande."""
    return _STYLESHEET.format(**palette_for(theme).as_dict())


# --- Icones -----------------------------------------------------------------
#: Jeu d'icones vectorielles original, dessine pour l'application.
#: Chaque entree est le contenu d'un chemin SVG sur une grille de 24x24.
_ICON_PATHS: Dict[str, str] = {
    "accueil": "M3 11.2 12 4l9 7.2V20a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z",
    "bibliotheque": "M4 5h5v14H4zM10.5 5h4v14h-4zM16.5 5.6l3.6 1 3 12.6-3.6-1z",
    "ecrans": "M3 5h18v10H3zM9 19h6M12 15v4",
    "horaires": "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zm0 4v5l3.5 2",
    "editeur": "M4 16.5 15.5 5l3.5 3.5L7.5 20H4zM13.5 7 17 10.5",
    "effets": "M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1"
               "M5.6 18.4l2.1-2.1M16.3 7.7l2.1-2.1M12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6z",
    "performances": "M3 17h3v4H3zM9.5 11h3v10h-3zM16 6h3v15h-3z",
    "historique": "M3 12a9 9 0 1 0 3-6.7V8m0 0H3m3 0V5M12 7v5l3.5 2",
    "parametres": "M12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6zM19.4 13a7.9 7.9 0 0 0 0-2l2-1.5-2-3.4"
                  "-2.3 1a8 8 0 0 0-1.7-1l-.3-2.5h-4l-.3 2.5a8 8 0 0 0-1.7 1l-2.3-1-2 3.4"
                  "L6.6 11a7.9 7.9 0 0 0 0 2l-2 1.5 2 3.4 2.3-1a8 8 0 0 0 1.7 1l.3 2.5h4"
                  "l.3-2.5a8 8 0 0 0 1.7-1l2.3 1 2-3.4z",
    "lecture": "M8 5.5v13l11-6.5z",
    "pause": "M8 5h3v14H8zM13 5h3v14h-3z",
    "ajouter": "M12 5v14M5 12h14",
    "dossier": "M3 7a1 1 0 0 1 1-1h5l2 2h8a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1z",
    "etoile": "M12 3.5l2.7 5.6 6.1.9-4.4 4.3 1 6.1-5.4-2.9-5.4 2.9 1-6.1L3.2 10l6.1-.9z",
    "recherche": "M11 4a7 7 0 1 0 0 14 7 7 0 0 0 0-14zM20 20l-4-4",
    "corbeille": "M4 7h16M9 7V5h6v2M6 7l1 13h10l1-13M10 11v6M14 11v6",
    "fermer": "M6 6l12 12M18 6L6 18",
    "nouveautes": "M12 3.6l1.9 4 4.4.6-3.2 3.1.8 4.3-3.9-2.1-3.9 2.1.8-4.3"
                   "-3.2-3.1 4.4-.6zM19 3v3M20.5 4.5h-3",
    "info": "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zm0 4.5v.5m0 3v6",
    "oeil": "M2 12s3.6-6.5 10-6.5S22 12 22 12s-3.6 6.5-10 6.5S2 12 2 12zm10-3a3 3 0 1 0 0 6 3 3 0 0 0 0-6z",
    "importer": "M12 3v11m0 0 4-4m-4 4-4-4M4 17v3h16v-3",
    "convertir": "M4 8h12l-3-3m3 3-3 3M20 16H8l3-3m-3 3 3 3",
}


def icon(name: str, color: str = "#e8ebf2", size: int = 22) -> QIcon:
    """Icone vectorielle du jeu interne, teintee a la demande."""
    path = _ICON_PATHS.get(name)
    if path is None:
        return QIcon()
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
        f'width="{size}" height="{size}" fill="none" stroke="{color}" '
        f'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">'
        f'<path d="{path}"/></svg>'
    )
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    pixmap = QPixmap(QSize(size, size))
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    return QIcon(pixmap)


def app_icon(size: int = 256) -> QIcon:
    """Icone originale : un ecran ouvert sur une nuit etoilee."""
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256"
        width="{size}" height="{size}">
      <defs>
        <linearGradient id="ciel" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stop-color="#2b1b6b"/>
          <stop offset="55%" stop-color="#7c5cff"/>
          <stop offset="100%" stop-color="#22d3ee"/>
        </linearGradient>
        <radialGradient id="halo" cx="0.68" cy="0.3" r="0.6">
          <stop offset="0%" stop-color="#ffffff" stop-opacity="0.85"/>
          <stop offset="100%" stop-color="#ffffff" stop-opacity="0"/>
        </radialGradient>
      </defs>
      <rect x="16" y="16" width="224" height="224" rx="54" fill="#0a0b14"/>
      <rect x="38" y="54" width="180" height="120" rx="18" fill="url(#ciel)"/>
      <circle cx="170" cy="92" r="34" fill="url(#halo)"/>
      <circle cx="72" cy="80" r="2.6" fill="#ffffff"/>
      <circle cx="104" cy="66" r="1.8" fill="#ffffff" opacity="0.9"/>
      <circle cx="90" cy="116" r="2.1" fill="#ffffff" opacity="0.8"/>
      <circle cx="136" cy="84" r="1.6" fill="#ffffff" opacity="0.75"/>
      <circle cx="60" cy="140" r="1.7" fill="#ffffff" opacity="0.7"/>
      <circle cx="190" cy="140" r="2.0" fill="#ffffff" opacity="0.65"/>
      <path d="M38 150c28-26 48 10 74-8s46 12 72-14v28a18 18 0 0 1-18 18H56a18 18 0 0 1-18-18z"
            fill="#0a0b14" opacity="0.5"/>
      <rect x="104" y="186" width="48" height="11" rx="5.5" fill="#7c5cff"/>
      <rect x="76" y="203" width="104" height="11" rx="5.5" fill="#272e4d"/>
    </svg>"""
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    pixmap = QPixmap(QSize(size, size))
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    return QIcon(pixmap)
