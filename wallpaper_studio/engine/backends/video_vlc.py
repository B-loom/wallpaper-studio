"""Lecture video par libVLC, rendue directement dans la fenetre de fond d'ecran.

libVLC dessine dans une fenetre native fournie par l'application
(``media_player_set_hwnd``). On lui confie un widget dedie, enfant de la
surface : le rendu reste ainsi entierement dans le processus graphique de VLC,
sans recopie d'images vers Python, ce qui est indispensable pour tenir la
cadence sur un processeur modeste.

Formats : la couverture depend des demultiplexeurs et decodeurs embarques dans
libVLC, pas d'une liste codee en dur. :meth:`VideoVlcBackend.start` signale une
erreur explicite quand un fichier ne peut pas etre lu.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QWidget

from ...media.types import FillMode
from ..playback import PlaybackRequest, PlaybackState
from .base import WallpaperBackend
from . import vlc_runtime

log = logging.getLogger(__name__)

#: Nombre de repetitions demande a libVLC pour une lecture en boucle.
_REPEAT_FOREVER = 65535

#: Correspondance entre nos modes de remplissage et le comportement de libVLC.
#: libVLC ne sait pas « rogner pour remplir » directement : on utilise le
#: rapport d'aspect force (``crop``) pour obtenir l'equivalent de COVER.
_VLC_CROP_MODES = {
    FillMode.COVER: True,
    FillMode.CONTAIN: False,
    FillMode.STRETCH: False,
    FillMode.CENTER: False,
    FillMode.TILE: False,
}


class VideoSurfaceWidget(QWidget):
    """Widget natif opaque qui recoit le rendu de libVLC."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_NativeWindow, True)
        self.setAttribute(Qt.WA_OpaquePaintEvent, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        # Fond noir : evite un flash blanc avant la premiere image decodee.
        palette = self.palette()
        palette.setColor(QPalette.Window, QColor(0, 0, 0))
        self.setPalette(palette)
        self.setAutoFillBackground(True)


class VideoVlcBackend(WallpaperBackend):
    """Moteur de rendu video base sur libVLC."""

    backend_name = "vlc"

    def __init__(
        self,
        request: PlaybackRequest,
        parent: Optional[QWidget] = None,
        hardware_decode: bool = True,
    ):
        super().__init__(request, parent)
        self._widget = VideoSurfaceWidget()
        self._player = None
        self._media = None
        self._hardware_decode = hardware_decode
        self._instance = None
        # Surveillance de fin de lecture : un fichier corrompu peut s'arreter
        # sans declencher d'erreur explicite.
        self._watchdog = QTimer(self)
        self._watchdog.setInterval(1500)
        self._watchdog.timeout.connect(self._check_health)
        self._health_ticks = 0
        self._registered = False
        self._failed_restarts = 0
        self._max_time_seen = 0

    def widget(self) -> QWidget:
        return self._widget

    @staticmethod
    def is_available() -> bool:
        return vlc_runtime.get_vlc_instance() is not None

    # --- Cycle de vie ------------------------------------------------------
    def start(self) -> bool:
        self._set_state(PlaybackState.LOADING)

        # libVLC ouvre les medias de maniere asynchrone : un chemin inexistant
        # ne provoque pas d'echec immediat de play(), le lecteur reste
        # simplement bloque. On verifie donc le fichier en amont pour pouvoir
        # signaler l'erreur tout de suite plutot qu'au bout du delai de garde.
        source = Path(self._request.path)
        if not source.exists():
            return self._fail("Fichier introuvable")
        if source.is_dir():
            return self._fail("Le chemin designe un dossier, pas une video")
        try:
            if source.stat().st_size == 0:
                return self._fail("Fichier video vide")
        except OSError as exc:
            return self._fail(f"Fichier inaccessible : {exc.strerror or exc}")

        self._instance = vlc_runtime.get_vlc_instance(self._hardware_decode)
        if self._instance is None:
            return self._fail(
                vlc_runtime.init_error() or "libVLC indisponible"
            )

        try:
            self._media = self._instance.media_new_path(self._request.path)
        except Exception as exc:  # noqa: BLE001
            return self._fail(f"Media refuse par libVLC : {exc}")
        if self._media is None:
            return self._fail("Fichier video illisible")

        if self._request.loop:
            self._media.add_option(f":input-repeat={_REPEAT_FOREVER}")
        if self._request.muted or self._request.volume <= 0:
            # Un fond muet n'a aucune raison d'ouvrir une sortie audio :
            # cela supprime un fil d'execution et ses tampons.
            self._media.add_option(":no-audio")
        if self._request.start_position > 0:
            self._media.add_option(f":start-time={self._request.start_position:.3f}")

        self._player = self._instance.media_player_new()
        if self._player is None:
            return self._fail("Lecteur libVLC indisponible")
        self._player.set_media(self._media)

        # Rendu dans notre fenetre native. winId() force la creation du HWND.
        self._widget.show()
        self._player.set_hwnd(int(self._widget.winId()))

        self._apply_fill_mode(self._request.fill_mode)
        self.set_muted(self._request.muted)
        self.set_volume(self._request.volume)

        if self._player.play() == -1:
            return self._fail("Lecture impossible (format non pris en charge ?)")

        if self._request.speed != 1.0:
            # La vitesse ne peut etre appliquee qu'une fois la lecture lancee.
            QTimer.singleShot(250, lambda: self.set_speed(self._request.speed))

        self._set_state(PlaybackState.PLAYING)
        self._watchdog.start()
        vlc_runtime.register_player()
        self._registered = True
        log.info(
            "Lecture video demarree : %s (materiel=%s)",
            self._request.path, self._hardware_decode,
        )
        return True

    def _apply_fill_mode(self, mode: FillMode) -> None:
        """Traduit le mode de remplissage en reglages libVLC.

        * ``COVER`` : on force le rapport d'aspect a celui de l'ecran, ce qui
          remplit toute la surface en rognant les bords.
        * ``STRETCH`` : identique, mais sans conserver les proportions.
        * ``CONTAIN`` / ``CENTER`` : reglages par defaut de libVLC, qui ajoute
          des bandes noires.
        """
        if self._player is None:
            return
        w = max(1, self._widget.width() or 1920)
        h = max(1, self._widget.height() or 1080)
        try:
            if mode is FillMode.COVER:
                self._player.video_set_aspect_ratio(None)
                self._player.video_set_crop_geometry(f"{w}:{h}".encode())
            elif mode is FillMode.STRETCH:
                self._player.video_set_crop_geometry(None)
                self._player.video_set_aspect_ratio(f"{w}:{h}".encode())
            else:
                self._player.video_set_crop_geometry(None)
                self._player.video_set_aspect_ratio(None)
        except Exception as exc:  # noqa: BLE001
            log.debug("Reglage du cadrage ignore par libVLC : %s", exc)

    def _check_health(self) -> None:
        """Detecte un arret inattendu et le signale a l'utilisateur."""
        if self._player is None:
            return
        vlc = vlc_runtime.vlc_module()
        state = self._player.get_state()
        if state == vlc.State.Error:
            self._watchdog.stop()
            self._fail("Erreur de lecture video (fichier corrompu ou codec absent)")
            return

        # Un fichier dont le conteneur est lisible mais le flux video absent ou
        # non decodable laisse le lecteur ouvert sans jamais afficher d'image.
        # Au bout de quelques cycles on previent plutot que de laisser un ecran
        # noir sans explication.
        self._health_ticks += 1
        if self._health_ticks >= 3:
            if state in (
                vlc.State.Opening, vlc.State.Buffering, vlc.State.NothingSpecial
            ):
                self._watchdog.stop()
                self._fail("La video ne demarre pas (flux illisible ou codec absent)")
                return
            # Critere decisif : une video reellement decodee a des dimensions.
            # libVLC peut annoncer « en lecture » pour un fichier qui n'est pas
            # une video ; l'absence de taille d'image le demasque.
            if not self._has_video_output():
                self._watchdog.stop()
                self._fail(
                    "Aucune image video dans ce fichier "
                    "(format non reconnu ou fichier corrompu)"
                )
                return

        # Memorise la progression reelle : elle distingue une vraie lecture
        # d'un fichier qui se « termine » aussitot ouvert.
        current = self._player.get_time()
        if current and current > self._max_time_seen:
            self._max_time_seen = current

        if state == vlc.State.Ended and self._request.loop:
            # input-repeat devrait relancer seul ; si l'etat reste Ended, on
            # redemarre explicitement plutot que de laisser un ecran fige.
            # Mais un fichier illisible « se termine » instantanement : relancer
            # sans compter creerait une boucle infinie qui masquerait l'erreur.
            if self._max_time_seen < 500:  # moins d'une demi-seconde lue
                self._failed_restarts += 1
                if self._failed_restarts >= 3:
                    self._watchdog.stop()
                    self._fail(
                        "La video se termine immediatement "
                        "(fichier tronque ou flux illisible)"
                    )
                    return
            else:
                self._failed_restarts = 0
            log.info("Fin de lecture inattendue, relance : %s", self._request.path)
            self._max_time_seen = 0
            self._player.stop()
            self._player.play()

    # --- Pilotage ----------------------------------------------------------
    def pause(self) -> None:
        if self._player is not None and self._player.is_playing():
            self._player.set_pause(1)
            self._watchdog.stop()
            self._set_state(PlaybackState.PAUSED)

    def resume(self) -> None:
        if self._player is not None and self._state == PlaybackState.PAUSED:
            self._player.set_pause(0)
            self._watchdog.start()
            self._set_state(PlaybackState.PLAYING)

    def stop(self) -> None:
        self._watchdog.stop()
        if self._registered:
            vlc_runtime.unregister_player()
            self._registered = False
        if self._player is not None:
            try:
                self._player.stop()
                # Detacher la fenetre avant de liberer evite que libVLC
                # continue a dessiner dans un HWND detruit.
                self._player.set_hwnd(0)
                self._player.release()
            except Exception as exc:  # noqa: BLE001
                log.debug("Liberation du lecteur : %s", exc)
            self._player = None
        if self._media is not None:
            try:
                self._media.release()
            except Exception:  # noqa: BLE001
                pass
            self._media = None
        self._set_state(PlaybackState.STOPPED)

    # --- Reglages ----------------------------------------------------------
    def set_volume(self, volume: int) -> None:
        if self._player is not None:
            self._player.audio_set_volume(max(0, min(100, int(volume))))

    def set_muted(self, muted: bool) -> None:
        if self._player is not None:
            self._player.audio_set_mute(bool(muted))

    def set_speed(self, speed: float) -> None:
        if self._player is not None:
            if self._player.set_rate(max(0.1, min(4.0, float(speed)))) == -1:
                log.debug("Vitesse de lecture non prise en charge pour ce media")

    def position(self) -> Optional[float]:
        """Position de lecture en secondes, ou ``None`` si indisponible."""
        if self._player is None:
            return None
        ms = self._player.get_time()
        return ms / 1000.0 if ms >= 0 else None

    def current_fps(self) -> Optional[float]:
        """Cadence annoncee par libVLC pour le flux en cours."""
        if self._player is None:
            return None
        try:
            fps = self._player.get_fps()
        except Exception:  # noqa: BLE001
            return None
        return fps if fps and fps > 0 else None

    def _has_video_output(self) -> bool:
        """Vrai si libVLC a reellement decode une image (dimensions connues)."""
        if self._player is None:
            return False
        try:
            width, height = self._player.video_get_size(0)
            return bool(width and height)
        except Exception:  # noqa: BLE001 - selon la version de libVLC
            return True  # dans le doute, on ne declare pas d'echec

    def has_audio(self) -> bool:
        if self._player is None:
            return False
        try:
            return self._player.audio_get_track_count() > 0
        except Exception:  # noqa: BLE001
            return False

    def apply_request(self, request: PlaybackRequest) -> bool:
        if request.path != self._request.path or request.kind != self._request.kind:
            return False
        if request.span_region != self._request.span_region:
            return False
        previous_mode = self._request.fill_mode
        self._request = request
        if request.fill_mode is not previous_mode:
            self._apply_fill_mode(request.fill_mode)
        self.set_volume(request.volume)
        self.set_muted(request.muted)
        self.set_speed(request.speed)
        return True
