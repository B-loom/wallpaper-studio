"""Interface commune des moteurs de rendu de fond d'ecran.

Chaque moteur sait afficher une famille de medias dans un widget Qt. Le moteur
principal (:mod:`wallpaper_studio.engine.wallpaper_engine`) ne connait que cette interface,
ce qui permet d'ajouter un type de contenu sans toucher au reste.
"""

from __future__ import annotations

import logging
from typing import Optional

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QWidget

from ..playback import PlaybackRequest, PlaybackState

log = logging.getLogger(__name__)


class WallpaperBackend(QObject):
    """Classe de base d'un moteur de rendu.

    Cycle de vie : ``__init__`` -> :meth:`start` -> (:meth:`pause` /
    :meth:`resume`) -> :meth:`stop`. Apres :meth:`stop` l'instance n'est plus
    reutilisable : le moteur en cree une nouvelle.
    """

    #: Emis lorsque la lecture echoue. Le message est destine a l'utilisateur.
    failed = Signal(str)
    #: Emis a chaque changement d'etat.
    state_changed = Signal(str)

    #: Nom affiche dans la page Performances.
    backend_name = "base"

    def __init__(self, request: PlaybackRequest, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._request = request
        self._state = PlaybackState.IDLE
        self._error: Optional[str] = None

    # --- Accesseurs --------------------------------------------------------
    @property
    def request(self) -> PlaybackRequest:
        return self._request

    @property
    def state(self) -> str:
        return self._state

    @property
    def error(self) -> Optional[str]:
        return self._error

    @property
    def is_animated(self) -> bool:
        """Vrai si le rendu consomme des ressources en continu."""
        return self._request.kind.is_animated

    def widget(self) -> QWidget:
        """Widget a inserer dans la surface. Doit exister des l'initialisation."""
        raise NotImplementedError

    # --- Pilotage ----------------------------------------------------------
    def start(self) -> bool:
        """Demarre le rendu. Retourne faux en cas d'echec (voir :attr:`error`)."""
        raise NotImplementedError

    def pause(self) -> None:
        """Suspend le rendu en liberant le maximum de ressources CPU."""

    def resume(self) -> None:
        """Reprend apres :meth:`pause`."""

    def stop(self) -> None:
        """Arrete definitivement et libere les ressources."""

    # --- Reglages a chaud --------------------------------------------------
    def set_volume(self, volume: int) -> None:
        """Volume de 0 a 100 ; sans effet sur un media muet."""

    def set_muted(self, muted: bool) -> None:
        pass

    def set_speed(self, speed: float) -> None:
        """Vitesse de lecture ; sans effet si le moteur ne la gere pas."""

    def set_fps_cap(self, fps: Optional[int]) -> None:
        """Plafond d'images par seconde ; sans effet si non applicable."""

    def apply_request(self, request: PlaybackRequest) -> bool:
        """Applique une nouvelle demande sans recreer le moteur si possible.

        Retourne vrai si la demande a pu etre appliquee a chaud. Faux signifie
        que le moteur doit etre remplace (changement de fichier, par exemple).
        """
        if request.path != self._request.path or request.kind != self._request.kind:
            return False
        self._request = request
        self.set_volume(request.volume)
        self.set_muted(request.muted)
        self.set_speed(request.speed)
        self.set_fps_cap(request.fps_cap)
        return True

    # --- Mesures -----------------------------------------------------------
    def current_fps(self) -> Optional[float]:
        """Images par seconde reellement rendues, si le moteur peut le mesurer.

        Retourne ``None`` quand la mesure n'est pas disponible : la page
        Performances affiche alors un tiret au lieu d'un chiffre fabrique.
        """
        return None

    # --- Interne -----------------------------------------------------------
    def _set_state(self, state: str) -> None:
        if state != self._state:
            self._state = state
            self.state_changed.emit(state)

    def _fail(self, message: str) -> bool:
        """Journalise, memorise et signale un echec. Retourne toujours faux."""
        self._error = message
        self._set_state(PlaybackState.ERROR)
        log.error("[%s] %s (%s)", self.backend_name, message, self._request.path)
        self.failed.emit(message)
        return False
