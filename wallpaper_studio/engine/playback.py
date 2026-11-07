"""Description d'une demande de lecture envoyee au moteur de rendu.

Un :class:`PlaybackRequest` est un objet immuable qui decrit *quoi* afficher et
*comment*. Il circule de l'interface (ou du planificateur) vers le moteur, ce
qui evite au moteur de dependre de la base de donnees.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Dict, Optional, Tuple

from ..media.types import FillMode, MediaKind


@dataclass(frozen=True)
class ImageAdjustments:
    """Corrections colorimetriques appliquees au rendu.

    Les valeurs neutres n'entrainent aucun traitement : le moteur detecte
    :attr:`is_neutral` et court-circuite la chaine de filtres.
    """

    brightness: float = 1.0   # 0.0 a 2.0
    contrast: float = 1.0     # 0.0 a 2.0
    saturation: float = 1.0   # 0.0 a 2.0
    hue: float = 0.0          # -180 a 180 degres
    blur: float = 0.0         # rayon en pixels
    rotation: int = 0         # 0, 90, 180, 270
    flip_h: bool = False
    flip_v: bool = False

    @property
    def is_neutral(self) -> bool:
        return (
            self.brightness == 1.0
            and self.contrast == 1.0
            and self.saturation == 1.0
            and self.hue == 0.0
            and self.blur == 0.0
            and self.rotation == 0
            and not self.flip_h
            and not self.flip_v
        )


@dataclass(frozen=True)
class EffectConfig:
    """Configuration d'un effet visuel superpose au fond d'ecran."""

    name: str
    enabled: bool = True
    intensity: float = 0.5           # 0.0 a 1.0
    options: Dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class PlaybackRequest:
    """Tout ce qu'il faut savoir pour afficher un fond d'ecran sur un ecran."""

    path: str
    kind: MediaKind
    fill_mode: FillMode = FillMode.COVER
    #: Volume de 0 a 100. Ignore pour les medias sans piste audio.
    volume: int = 0
    muted: bool = True
    loop: bool = True
    #: Vitesse de lecture ; 1.0 = vitesse normale.
    speed: float = 1.0
    #: Position de depart en secondes.
    start_position: float = 0.0
    adjustments: ImageAdjustments = field(default_factory=ImageAdjustments)
    effects: Tuple[EffectConfig, ...] = ()
    #: Plafond d'images par seconde ; ``None`` = sans limite imposee.
    fps_cap: Optional[int] = None
    #: Identifiant de l'entree de bibliotheque, pour l'historique.
    media_id: Optional[int] = None
    #: Rendu panoramique : rectangle du media a afficher sur cet ecran, en
    #: fractions (x, y, largeur, hauteur) de l'image complete.
    span_region: Optional[Tuple[float, float, float, float]] = None

    def with_(self, **kwargs) -> "PlaybackRequest":
        """Copie modifiee de la demande."""
        return replace(self, **kwargs)

    @property
    def needs_audio(self) -> bool:
        return not self.muted and self.volume > 0

    @property
    def active_effects(self) -> Tuple[EffectConfig, ...]:
        return tuple(e for e in self.effects if e.enabled and e.intensity > 0)


class PlaybackState(str):
    """Etats possibles d'un moteur de rendu."""

    IDLE = "idle"
    LOADING = "loading"
    PLAYING = "playing"
    PAUSED = "paused"
    ERROR = "error"
    STOPPED = "stopped"
