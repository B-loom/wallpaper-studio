"""Rendu des images fixes et des images animees (GIF, APNG, WEBP anime).

Deux strategies selon le contenu :

* **Image fixe** : decodee une fois, corrections appliquees, puis simplement
  recopiee a chaque repeint. Cout processeur nul en regime permanent.
* **Image animee** : toutes les images sont decodees et corrigees au chargement
  (voir :func:`wallpaper_studio.media.image_ops.load_animation_frames`), puis affichees par
  un minuteur. Si l'animation est trop volumineuse pour la memoire, on se rabat
  sur ``QMovie``, qui decode a la volee sans corrections colorimetriques.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from PySide6.QtCore import Qt, QRect, QTimer
from PySide6.QtGui import QMovie, QPainter, QPixmap
from PySide6.QtWidgets import QWidget

from ...media.image_ops import compute_fill_rects, load_animation_frames, load_static_image
from ...media.types import FillMode, MediaKind
from ..playback import PlaybackRequest, PlaybackState
from .base import WallpaperBackend

log = logging.getLogger(__name__)

#: Reduction appliquee aux sources enormes, relativement a la taille de l'ecran.
MAX_SIDE_FACTOR = 2


class ImageCanvas(QWidget):
    """Widget qui dessine un ``QPixmap`` selon un mode de remplissage."""

    def __init__(self, fill_mode: FillMode = FillMode.COVER, parent=None):
        super().__init__(parent)
        self._pixmap: Optional[QPixmap] = None
        self._fill_mode = fill_mode
        self.setAttribute(Qt.WA_OpaquePaintEvent, True)
        self.setAutoFillBackground(False)

    def set_pixmap(self, pixmap: Optional[QPixmap]) -> None:
        self._pixmap = pixmap
        self.update()

    def set_fill_mode(self, mode: FillMode) -> None:
        if mode is not self._fill_mode:
            self._fill_mode = mode
            self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - API Qt
        painter = QPainter(self)
        painter.fillRect(self.rect(), Qt.black)
        pm = self._pixmap
        if pm is None or pm.isNull():
            return

        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        dst_size = (self.width(), self.height())

        if self._fill_mode is FillMode.TILE:
            painter.drawTiledPixmap(self.rect(), pm)
            return

        src, dst = compute_fill_rects((pm.width(), pm.height()), dst_size, self._fill_mode)
        painter.drawPixmap(QRect(*dst), pm, QRect(*src))


class ImageBackend(WallpaperBackend):
    """Moteur de rendu pour images fixes et animees."""

    backend_name = "image"

    def __init__(self, request: PlaybackRequest, parent: Optional[QWidget] = None):
        super().__init__(request, parent)
        self._canvas = ImageCanvas(request.fill_mode)
        self._frames: List[QPixmap] = []
        self._delays: List[int] = []
        self._index = 0
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.PreciseTimer)
        self._timer.timeout.connect(self._next_frame)
        self._movie: Optional[QMovie] = None
        self._fps_cap: Optional[int] = request.fps_cap

    def widget(self) -> QWidget:
        return self._canvas

    # --- Cycle de vie ------------------------------------------------------
    def start(self) -> bool:
        self._set_state(PlaybackState.LOADING)
        req = self._request
        # La surface a deja sa taille finale : on s'en sert pour eviter de
        # garder en memoire une image bien plus grande que l'ecran.
        max_side = None
        if self._canvas.width() > 0:
            max_side = MAX_SIDE_FACTOR * max(self._canvas.width(), self._canvas.height())

        try:
            if req.kind is MediaKind.ANIMATED_IMAGE:
                return self._start_animated(max_side)
            return self._start_static(max_side)
        except FileNotFoundError:
            return self._fail("Fichier introuvable")
        except MemoryError as exc:
            log.warning("Pre-calcul impossible (%s) ; repli sur QMovie", exc)
            return self._start_movie_fallback()
        except Exception as exc:  # noqa: BLE001 - formats et fichiers varies
            return self._fail(f"Image illisible : {exc}")

    def _start_static(self, max_side: Optional[int]) -> bool:
        qimg = load_static_image(
            self._request.path,
            adjustments=self._request.adjustments,
            span_region=self._request.span_region,
            max_side=max_side,
        )
        self._canvas.set_pixmap(QPixmap.fromImage(qimg))
        self._set_state(PlaybackState.PLAYING)
        return True

    def _start_animated(self, max_side: Optional[int]) -> bool:
        self._frames, self._delays = load_animation_frames(
            self._request.path,
            adjustments=self._request.adjustments,
            span_region=self._request.span_region,
            max_side=max_side,
        )
        if len(self._frames) == 1:
            # Fichier annonce anime mais contenant une seule image.
            self._canvas.set_pixmap(self._frames[0])
            self._set_state(PlaybackState.PLAYING)
            return True

        log.info(
            "Animation pre-calculee : %s images, %s",
            len(self._frames), self._request.path,
        )
        self._index = 0
        self._canvas.set_pixmap(self._frames[0])
        self._set_state(PlaybackState.PLAYING)
        self._schedule_next()
        return True

    def _start_movie_fallback(self) -> bool:
        """Decodage a la volee par QMovie, sans corrections colorimetriques."""
        self._movie = QMovie(self._request.path)
        if not self._movie.isValid():
            return self._fail("Animation illisible")
        self._movie.setCacheMode(QMovie.CacheNone)
        self._movie.frameChanged.connect(self._on_movie_frame)
        if self._request.speed != 1.0:
            self._movie.setSpeed(int(self._request.speed * 100))
        self._movie.start()
        self._set_state(PlaybackState.PLAYING)
        return True

    def _on_movie_frame(self) -> None:
        if self._movie:
            self._canvas.set_pixmap(self._movie.currentPixmap())

    # --- Animation pre-calculee -------------------------------------------
    def _effective_delay(self, base_ms: int) -> int:
        """Duree d'affichage, vitesse et plafond FPS pris en compte."""
        speed = max(0.05, self._request.speed)
        delay = base_ms / speed
        if self._fps_cap:
            delay = max(delay, 1000.0 / max(1, self._fps_cap))
        return max(10, int(round(delay)))

    def _schedule_next(self) -> None:
        if not self._delays:
            return
        self._timer.start(self._effective_delay(self._delays[self._index]))

    def _next_frame(self) -> None:
        if not self._frames:
            return
        self._index += 1
        if self._index >= len(self._frames):
            if not self._request.loop:
                self._timer.stop()
                self._index = len(self._frames) - 1
                return
            self._index = 0
        self._canvas.set_pixmap(self._frames[self._index])
        self._schedule_next()

    # --- Pilotage ----------------------------------------------------------
    def pause(self) -> None:
        self._timer.stop()
        if self._movie:
            self._movie.setPaused(True)
        if self.is_animated:
            self._set_state(PlaybackState.PAUSED)

    def resume(self) -> None:
        if self._movie:
            self._movie.setPaused(False)
            self._set_state(PlaybackState.PLAYING)
            return
        if self._frames and len(self._frames) > 1:
            self._set_state(PlaybackState.PLAYING)
            self._schedule_next()

    def stop(self) -> None:
        self._timer.stop()
        if self._movie:
            self._movie.stop()
            self._movie.deleteLater()
            self._movie = None
        # Liberer explicitement : une animation longue peut peser des dizaines
        # de megaoctets, et le ramasse-miettes de Python n'est pas immediat.
        self._frames.clear()
        self._delays.clear()
        self._canvas.set_pixmap(None)
        self._set_state(PlaybackState.STOPPED)

    def set_speed(self, speed: float) -> None:
        if self._movie:
            self._movie.setSpeed(max(1, int(speed * 100)))

    def set_fps_cap(self, fps: Optional[int]) -> None:
        self._fps_cap = fps

    def current_fps(self) -> Optional[float]:
        """Cadence theorique de l'animation en cours.

        Il s'agit de la cadence du contenu, pas d'une mesure du rendu : les
        images etant pre-calculees, les deux coincident sauf saturation du
        systeme.
        """
        if not self._delays:
            return None
        avg = sum(self._effective_delay(d) for d in self._delays) / len(self._delays)
        return 1000.0 / avg if avg else None

    def apply_request(self, request: PlaybackRequest) -> bool:
        """Le mode de remplissage et la vitesse changent a chaud.

        Un changement de corrections colorimetriques impose un redecodage : on
        retourne alors faux pour que le moteur recree l'instance.
        """
        if request.path != self._request.path or request.kind != self._request.kind:
            return False
        if request.adjustments != self._request.adjustments:
            return False
        if request.span_region != self._request.span_region:
            return False
        self._request = request
        self._canvas.set_fill_mode(request.fill_mode)
        self.set_speed(request.speed)
        self.set_fps_cap(request.fps_cap)
        return True
