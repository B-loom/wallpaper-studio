"""Moteur de fonds d'ecran : orchestre surfaces, moteurs de rendu et ecrans.

Responsabilites
---------------
* maintenir une :class:`~wallpaper_studio.engine.surface.WallpaperSurface` par ecran gere ;
* choisir le moteur de rendu adapte au type de media ;
* appliquer, mettre en pause, reprendre et arreter les fonds ;
* suivre les changements de configuration d'ecrans ;
* survivre a un redemarrage de l'Explorateur Windows.

Toutes les methodes publiques doivent etre appelees depuis le fil de
l'interface : Qt n'autorise pas la manipulation de widgets depuis un autre fil.
Le planificateur, qui tourne dans son propre fil, passe par un signal Qt
(voir :class:`wallpaper_studio.ui.main_window.MainWindow`) plutot que d'appeler le moteur
directement.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple

from PySide6.QtCore import QObject, QTimer, Signal

from ..media.types import FillMode, MediaKind
from ..system import win_desktop as wd
from ..system.monitors import MonitorInfo, MonitorManager
from .backends.base import WallpaperBackend
from .backends.image_backend import ImageBackend
from .backends.video_vlc import VideoVlcBackend
from .effects import EffectsOverlay
from .playback import PlaybackRequest, PlaybackState
from .surface import WallpaperSurface

log = logging.getLogger(__name__)

#: Delai avant de liberer libVLC une fois la derniere video arretee.
VLC_IDLE_RELEASE_MS = 20_000


@dataclass
class ScreenState:
    """Etat courant d'un ecran gere par le moteur."""

    monitor: MonitorInfo
    surface: WallpaperSurface
    backend: Optional[WallpaperBackend] = None
    request: Optional[PlaybackRequest] = None
    overlay: Optional["EffectsOverlay"] = None
    paused: bool = False
    error: Optional[str] = None

    @property
    def is_playing(self) -> bool:
        return self.backend is not None and self.backend.state == PlaybackState.PLAYING

    @property
    def media_path(self) -> Optional[str]:
        return self.request.path if self.request else None


class WallpaperEngine(QObject):
    """Point d'entree unique pour afficher des fonds d'ecran."""

    #: (cle_ecran, message) lorsqu'un rendu echoue.
    playback_failed = Signal(str, str)
    #: (cle_ecran) lorsqu'un fond a ete applique avec succes.
    wallpaper_applied = Signal(str)
    #: Emis quand la configuration des ecrans a change.
    monitors_changed = Signal()
    #: Emis lorsque le moteur a du se rattacher au bureau.
    host_recovered = Signal()

    def __init__(
        self,
        monitor_manager: Optional[MonitorManager] = None,
        hardware_decode: bool = True,
        fps_cap: Optional[int] = None,
        parent: Optional[QObject] = None,
    ):
        super().__init__(parent)
        self._monitors = monitor_manager or MonitorManager()
        self._host: Optional[wd.WallpaperHost] = None
        self._screens: Dict[str, ScreenState] = {}
        self._hardware_decode = hardware_decode
        self._fps_cap = fps_cap
        self._global_paused = False
        self._started = False

        # Surveillance du support : un redemarrage de l'Explorateur detruit la
        # couche WorkerW et nos fenetres se retrouvent orphelines.
        self._host_watch = QTimer(self)
        # Un redemarrage de l'Explorateur est exceptionnel.
        self._host_watch.setInterval(10000)
        self._host_watch.timeout.connect(self._check_host)

        # libVLC occupe environ 85 Mo (greffons, decodeurs, tampons). Quand
        # plus aucune video n'est affichee, cette memoire ne sert a rien : on
        # la rend, apres un court delai pour ne pas tout recharger si
        # l'utilisateur enchaine deux videos.
        self._vlc_idle = QTimer(self)
        self._vlc_idle.setSingleShot(True)
        self._vlc_idle.setInterval(VLC_IDLE_RELEASE_MS)
        self._vlc_idle.timeout.connect(self._release_vlc_if_idle)

    # --- Proprietes --------------------------------------------------------
    @property
    def monitor_manager(self) -> MonitorManager:
        return self._monitors

    @property
    def screens(self) -> Dict[str, ScreenState]:
        return dict(self._screens)

    @property
    def is_paused(self) -> bool:
        return self._global_paused

    @property
    def host(self) -> Optional[wd.WallpaperHost]:
        return self._host

    @property
    def active_count(self) -> int:
        return sum(1 for s in self._screens.values() if s.is_playing)

    @property
    def animated_count(self) -> int:
        """Nombre de rendus animes en cours (videos, GIF, scenes web)."""
        return sum(
            1
            for s in self._screens.values()
            if s.is_playing and s.backend and s.backend.is_animated
        )

    def state_for(self, monitor_key: str) -> Optional[ScreenState]:
        return self._screens.get(monitor_key)

    # --- Demarrage / arret -------------------------------------------------
    def start(self) -> bool:
        """Prepare le moteur : support du bureau et surfaces par ecran."""
        if self._started:
            return True
        self._host = wd.find_wallpaper_host()
        if self._host is None:
            log.error("Impossible de preparer la couche de fond d'ecran")
            return False
        if self._host.is_fallback:
            log.warning(
                "Rendu sur Progman : les icones du bureau peuvent scintiller"
            )
        self._sync_surfaces()
        self._host_watch.start()
        self._started = True
        log.info("Moteur demarre (%s ecran(s))", len(self._screens))
        return True

    def shutdown(self) -> None:
        """Arrete tous les rendus et libere les ressources."""
        self._host_watch.stop()
        self._vlc_idle.stop()
        for key in list(self._screens):
            self._teardown_screen(key)
        self._screens.clear()
        from .backends import vlc_runtime

        # Tous les lecteurs viennent d'etre arretes : liberation inconditionnelle.
        vlc_runtime.release_vlc_instance(force=True)
        wd.refresh_desktop()
        self._started = False
        log.info("Moteur arrete et ressources liberees")

    def _teardown_screen(self, key: str) -> None:
        state = self._screens.get(key)
        if state is None:
            return
        if state.backend is not None:
            state.backend.stop()
            state.backend.deleteLater()
            state.backend = None
        if state.overlay is not None:
            state.overlay.pause()
            state.overlay.deleteLater()
            state.overlay = None
        state.surface.set_overlay(None)
        state.surface.set_content(None)
        state.surface.detach()
        state.surface.close()
        state.surface.deleteLater()

    # --- Gestion des surfaces ---------------------------------------------
    def _sync_surfaces(self) -> None:
        """Cree, deplace ou supprime les surfaces selon les ecrans presents."""
        if self._host is None:
            return
        current = {m.key: m for m in self._monitors.monitors}

        for key in list(self._screens):
            if key not in current:
                log.info("Ecran retire : %s", key)
                self._teardown_screen(key)
                del self._screens[key]

        for key, monitor in current.items():
            state = self._screens.get(key)
            if state is None:
                surface = WallpaperSurface(monitor)
                if not surface.attach(self._host):
                    log.error("Surface non rattachee pour %s", monitor.label)
                self._screens[key] = ScreenState(monitor=monitor, surface=surface)
                log.info("Ecran pris en charge : %s", monitor.describe())
            elif state.monitor.rect != monitor.rect:
                state.monitor = monitor
                state.surface.update_monitor(monitor)

    def refresh_monitors(self) -> bool:
        """Releve la configuration des ecrans. Vrai si quelque chose a change."""
        change = self._monitors.refresh()
        if change.any:
            self._sync_surfaces()
            self.monitors_changed.emit()
        return change.any

    def _check_host(self) -> None:
        """Detecte la perte du support et rattache les surfaces le cas echeant."""
        if self._host is not None and wd.host_is_alive(self._host):
            return
        log.warning("Couche de fond d'ecran perdue (redemarrage de l'Explorateur ?)")
        new_host = wd.find_wallpaper_host()
        if new_host is None:
            return
        self._host = new_host
        for state in self._screens.values():
            state.surface.reattach(new_host)
        log.info("Surfaces rattachees au nouveau support")
        self.host_recovered.emit()

    # --- Choix du moteur de rendu -----------------------------------------
    def _make_backend(self, request: PlaybackRequest) -> Optional[WallpaperBackend]:
        kind = request.kind
        if kind in (MediaKind.IMAGE, MediaKind.ANIMATED_IMAGE):
            return ImageBackend(request)
        if kind is MediaKind.VIDEO:
            if not VideoVlcBackend.is_available():
                from .backends import vlc_runtime

                log.error("Lecture video impossible : %s", vlc_runtime.init_error())
                return None
            return VideoVlcBackend(request, hardware_decode=self._hardware_decode)
        if kind is MediaKind.WEB:
            from .backends.web_backend import WebBackend

            if not WebBackend.is_available():
                log.error("Les fonds web necessitent QtWebEngine, absent de cette installation")
                return None
            return WebBackend(request)
        log.error("Type de media non pris en charge : %s", kind)
        return None

    # --- Application d'un fond --------------------------------------------
    def apply(self, monitor_key: str, request: PlaybackRequest) -> bool:
        """Affiche un fond d'ecran sur un ecran donne.

        Si le media et les corrections sont identiques a ceux deja affiches, le
        moteur existant est simplement reconfigure : pas de coupure visible.
        """
        state = self._screens.get(monitor_key)
        if state is None:
            log.error("Ecran inconnu : %s", monitor_key)
            return False

        request = request.with_(
            fps_cap=request.fps_cap if request.fps_cap is not None else self._fps_cap
        )

        # Reconfiguration a chaud quand c'est possible.
        if state.backend is not None and state.backend.state in (
            PlaybackState.PLAYING, PlaybackState.PAUSED
        ):
            if state.backend.apply_request(request):
                state.request = request
                log.debug("Reglages appliques a chaud sur %s", monitor_key)
                self.wallpaper_applied.emit(monitor_key)
                return True

        backend = self._make_backend(request)
        if backend is None:
            message = f"Aucun moteur disponible pour {request.kind.label.lower()}"
            state.error = message
            self.playback_failed.emit(monitor_key, message)
            return False

        backend.failed.connect(
            lambda msg, key=monitor_key: self._on_backend_failed(key, msg)
        )

        # L'ancien moteur n'est arrete qu'une fois le nouveau pret, ce qui
        # reduit le temps d'ecran noir entre deux fonds.
        previous = state.backend
        state.surface.set_content(backend.widget())

        if not backend.start():
            message = backend.error or "Lecture impossible"
            state.error = message
            backend.stop()
            backend.deleteLater()
            if previous is not None:
                state.surface.set_content(previous.widget())
            self.playback_failed.emit(monitor_key, message)
            return False

        if previous is not None:
            previous.stop()
            previous.deleteLater()

        state.backend = backend
        state.request = request
        state.error = None
        state.paused = False
        self._sync_overlay(state, request)

        if self._global_paused:
            backend.pause()
            state.paused = True

        log.info(
            "Fond applique sur %s : %s (%s)",
            state.monitor.label, request.path, backend.backend_name,
        )
        self._schedule_vlc_check()
        self.wallpaper_applied.emit(monitor_key)
        return True

    def apply_to_all(self, request: PlaybackRequest) -> int:
        """Applique le meme fond a tous les ecrans. Retourne le nombre de reussites."""
        return sum(1 for key in list(self._screens) if self.apply(key, request))

    def apply_span(self, request: PlaybackRequest) -> int:
        """Repartit une image panoramique sur l'ensemble des ecrans.

        Chaque ecran recoit la portion du media correspondant a sa position
        dans le bureau virtuel. Les ecrans de tailles differentes sont geres :
        la decoupe suit les rectangles reels.
        """
        bx, by, bw, bh = self._monitors.bounding_rect()
        if bw <= 0 or bh <= 0:
            return 0
        count = 0
        for key, state in self._screens.items():
            x, y, w, h = state.monitor.rect
            region = ((x - bx) / bw, (y - by) / bh, w / bw, h / bh)
            if self.apply(key, request.with_(span_region=region, fill_mode=FillMode.STRETCH)):
                count += 1
        return count

    def clear(self, monitor_key: str) -> None:
        """Retire le fond d'un ecran et libere son moteur de rendu."""
        state = self._screens.get(monitor_key)
        if state is None or state.backend is None:
            return
        state.backend.stop()
        state.backend.deleteLater()
        state.backend = None
        state.request = None
        if state.overlay is not None:
            state.overlay.pause()
            state.surface.set_overlay(None)
            state.overlay.deleteLater()
            state.overlay = None
        state.surface.set_content(None)
        self._schedule_vlc_check()
        log.info("Fond retire de %s", state.monitor.label)

    # --- Pause / reprise ---------------------------------------------------
    def pause_all(self, reason: str = "") -> None:
        """Suspend tous les rendus animes (economie de ressources)."""
        if self._global_paused:
            return
        self._global_paused = True
        for state in self._screens.values():
            if state.backend is not None:
                state.backend.pause()
                state.paused = True
            if state.overlay is not None:
                state.overlay.pause()
        log.info("Rendus en pause%s", f" ({reason})" if reason else "")

    def resume_all(self, reason: str = "") -> None:
        if not self._global_paused:
            return
        self._global_paused = False
        for state in self._screens.values():
            if state.backend is not None:
                state.backend.resume()
                state.paused = False
            if state.overlay is not None:
                state.overlay.resume()
        log.info("Rendus repris%s", f" ({reason})" if reason else "")

    def pause_screen(self, monitor_key: str) -> None:
        state = self._screens.get(monitor_key)
        if state and state.backend:
            state.backend.pause()
            state.paused = True
            if state.overlay is not None:
                state.overlay.pause()

    def resume_screen(self, monitor_key: str) -> None:
        state = self._screens.get(monitor_key)
        if state and state.backend:
            state.backend.resume()
            state.paused = False
            if state.overlay is not None:
                state.overlay.resume()

    # --- Reglages globaux --------------------------------------------------
    def set_fps_cap(self, fps: Optional[int]) -> None:
        self._fps_cap = fps
        for state in self._screens.values():
            if state.backend is not None:
                state.backend.set_fps_cap(fps)

    def set_hardware_decode(self, enabled: bool) -> None:
        """Change le mode de decodage. Les videos en cours sont relancees."""
        if enabled == self._hardware_decode:
            return
        self._hardware_decode = enabled
        for key, state in list(self._screens.items()):
            if state.request and state.request.kind is MediaKind.VIDEO:
                request = state.request
                self.clear(key)
                self.apply(key, request)

    def set_volume(self, monitor_key: str, volume: int, muted: Optional[bool] = None) -> None:
        state = self._screens.get(monitor_key)
        if state is None or state.backend is None:
            return
        state.backend.set_volume(volume)
        if muted is not None:
            state.backend.set_muted(muted)
        if state.request is not None:
            state.request = state.request.with_(
                volume=volume, muted=state.request.muted if muted is None else muted
            )

    # --- Effets visuels ----------------------------------------------------
    def _sync_overlay(self, state: ScreenState, request: PlaybackRequest) -> None:
        """Installe ou retire la couche d'effets selon la demande."""
        effects = request.active_effects
        if not effects:
            if state.overlay is not None:
                state.overlay.pause()
                state.surface.set_overlay(None)
                state.overlay.deleteLater()
                state.overlay = None
            return

        fps = self._fps_cap or 30
        if state.overlay is None:
            overlay = EffectsOverlay(effects, fps=fps)
            state.surface.set_overlay(overlay)
            state.overlay = overlay
        else:
            state.overlay.set_fps(fps)
            state.overlay.set_effects(effects)
        log.info(
            "Effets actifs sur %s : %s (%s particules)",
            state.monitor.label,
            ", ".join(e.name for e in effects),
            state.overlay.particle_count,
        )

    def set_mouse_position(self, x: int, y: int) -> None:
        """Transmet la position du curseur aux effets et fonds interactifs.

        Les fenetres de fond d'ecran ne recoivent pas les evenements souris du
        bureau : la position vient d'un suivi global (voir
        :class:`wallpaper_studio.system.mouse.MouseTracker`).
        """
        for state in self._screens.values():
            mx, my = state.monitor.rect[0], state.monitor.rect[1]
            local_x, local_y = x - mx, y - my
            if state.overlay is not None:
                state.overlay.set_mouse(local_x, local_y)
            backend = state.backend
            if backend is not None and hasattr(backend, "update_mouse"):
                backend.update_mouse(local_x, local_y)

    # --- Liberation de libVLC --------------------------------------------
    def _video_backends_active(self) -> bool:
        return any(
            state.backend is not None
            and state.backend.backend_name == "vlc"
            for state in self._screens.values()
        )

    def _schedule_vlc_check(self) -> None:
        """Arme ou annule la liberation de libVLC selon l'etat des ecrans."""
        if self._video_backends_active():
            self._vlc_idle.stop()
        elif not self._vlc_idle.isActive():
            self._vlc_idle.start()

    def _release_vlc_if_idle(self) -> None:
        if self._video_backends_active():
            return
        from .backends import vlc_runtime

        if vlc_runtime.instance_is_loaded():
            vlc_runtime.release_vlc_instance()
            log.info("libVLC liberee : plus aucune video affichee")
            from ..system.memory import trim_working_set

            trim_working_set("libVLC liberee")

    def _on_backend_failed(self, monitor_key: str, message: str) -> None:
        state = self._screens.get(monitor_key)
        if state is not None:
            state.error = message
        log.error("Rendu en echec sur %s : %s", monitor_key, message)
        self.playback_failed.emit(monitor_key, message)

    # --- Mesures -----------------------------------------------------------
    def fps_report(self) -> Dict[str, Optional[float]]:
        """Cadence par ecran ; ``None`` quand la mesure n'est pas disponible."""
        return {
            key: (state.backend.current_fps() if state.backend else None)
            for key, state in self._screens.items()
        }
