"""Moteur de rendu : ecrans, erreurs de lecture, pause et liberation.

Ces tests pilotent de vrais widgets Qt et de vrais fichiers medias. Ils ne
rattachent pas les surfaces au bureau pour ne pas perturber le fond d'ecran de
la machine qui execute la suite de tests : c'est le rendu et la gestion des
ressources qui sont verifies, pas l'integration Windows (couverte par
``main.py --selftest``).
"""

from __future__ import annotations

import gc
from pathlib import Path

import pytest

from wallpaper_studio.engine.backends.image_backend import ImageBackend
from wallpaper_studio.engine.backends.video_vlc import VideoVlcBackend
from wallpaper_studio.engine.playback import ImageAdjustments, PlaybackRequest, PlaybackState
from wallpaper_studio.media.image_ops import compute_fill_rects
from wallpaper_studio.media.probe import probe_media
from wallpaper_studio.media.types import FillMode, MediaKind

pytestmark = pytest.mark.usefixtures("qapp")


def process(ms: int = 60) -> None:
    """Laisse Qt traiter ses evenements pendant un court instant."""
    from PySide6.QtCore import QEventLoop, QTimer
    from PySide6.QtWidgets import QApplication

    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()
    QApplication.processEvents()


# --- Detection des ecrans ---------------------------------------------------
class TestDetectionEcrans:
    def test_au_moins_un_ecran_detecte(self):
        from wallpaper_studio.system.monitors import enumerate_monitors

        monitors = enumerate_monitors()
        assert monitors, "aucun ecran detecte"
        assert sum(1 for m in monitors if m.is_primary) == 1

    def test_informations_coherentes(self):
        from wallpaper_studio.system.monitors import enumerate_monitors

        for monitor in enumerate_monitors():
            assert monitor.width > 0 and monitor.height > 0
            assert monitor.key
            assert monitor.dpi >= 72
            assert monitor.orientation in ("paysage", "portrait")

    def test_cle_stable_entre_deux_releves(self):
        from wallpaper_studio.system.monitors import enumerate_monitors

        first = {m.key for m in enumerate_monitors()}
        second = {m.key for m in enumerate_monitors()}
        assert first == second

    def test_detection_des_changements(self):
        from wallpaper_studio.system.monitors import MonitorManager

        manager = MonitorManager()
        assert manager.count >= 1
        assert manager.refresh().any is False

    def test_rectangle_englobant(self):
        from wallpaper_studio.system.monitors import MonitorManager

        manager = MonitorManager()
        _, _, width, height = manager.bounding_rect()
        assert width > 0 and height > 0


# --- Modes de remplissage ---------------------------------------------------
class TestModesRemplissage:
    def test_cover_remplit_toute_la_destination(self):
        _, dst = compute_fill_rects((1600, 900), (1920, 1080), FillMode.COVER)
        assert dst == (0, 0, 1920, 1080)

    def test_cover_rogne_la_source_si_proportions_differentes(self):
        src, dst = compute_fill_rects((2000, 500), (1000, 1000), FillMode.COVER)
        assert dst == (0, 0, 1000, 1000)
        # Source large et destination carree : on ne garde qu'une bande centrale.
        assert src[2] < 2000
        assert src[0] > 0, "la portion visible doit etre centree"

    def test_contain_conserve_les_proportions(self):
        _, dst = compute_fill_rects((1000, 500), (1000, 1000), FillMode.CONTAIN)
        assert dst[2] == 1000
        assert dst[3] == 500
        assert dst[1] == 250, "l'image doit etre centree verticalement"

    def test_stretch_occupe_tout_sans_rogner(self):
        src, dst = compute_fill_rects((800, 600), (1920, 1080), FillMode.STRETCH)
        assert src == (0, 0, 800, 600)
        assert dst == (0, 0, 1920, 1080)

    def test_center_n_agrandit_pas_une_petite_image(self):
        _, dst = compute_fill_rects((200, 100), (1000, 800), FillMode.CENTER)
        assert dst[2] == 200 and dst[3] == 100
        assert dst[0] == 400 and dst[1] == 350


# --- Rendu des images -------------------------------------------------------
class TestRenduImages:
    def _backend(self, path, kind, **kw):
        request = PlaybackRequest(path=str(path), kind=kind, **kw)
        backend = ImageBackend(request)
        backend.widget().resize(640, 360)
        return backend

    def test_image_fixe(self, media_files):
        backend = self._backend(media_files["image"], MediaKind.IMAGE)
        assert backend.start() is True
        assert backend.state == PlaybackState.PLAYING
        assert backend.error is None
        backend.stop()
        assert backend.state == PlaybackState.STOPPED

    def test_image_avec_corrections(self, media_files):
        backend = self._backend(
            media_files["image"], MediaKind.IMAGE,
            adjustments=ImageAdjustments(brightness=1.4, saturation=0.5, blur=1.5,
                                         rotation=90, flip_h=True),
        )
        assert backend.start() is True
        backend.stop()

    def test_animation_pre_calculee(self, media_files):
        backend = self._backend(media_files["gif"], MediaKind.ANIMATED_IMAGE)
        assert backend.start() is True
        assert backend.is_animated
        # Le GIF de test a 4 images.
        assert len(backend._frames) == 4
        assert backend.current_fps() is not None
        process(260)
        backend.stop()
        assert backend._frames == [], "les images doivent etre liberees a l'arret"

    def test_pause_et_reprise_d_une_animation(self, media_files):
        backend = self._backend(media_files["gif"], MediaKind.ANIMATED_IMAGE)
        backend.start()
        backend.pause()
        assert backend.state == PlaybackState.PAUSED
        backend.resume()
        assert backend.state == PlaybackState.PLAYING
        backend.stop()

    def test_fichier_manquant_signale(self, media_files):
        backend = self._backend(media_files["absent"], MediaKind.IMAGE)
        assert backend.start() is False
        assert backend.state == PlaybackState.ERROR
        assert "introuvable" in backend.error.lower()

    def test_fichier_illisible_signale(self, media_files):
        backend = self._backend(media_files["broken"], MediaKind.IMAGE)
        assert backend.start() is False
        assert backend.state == PlaybackState.ERROR
        assert backend.error

    def test_changement_de_cadrage_a_chaud(self, media_files):
        backend = self._backend(media_files["image"], MediaKind.IMAGE)
        backend.start()
        nouvelle = backend.request.with_(fill_mode=FillMode.CONTAIN)
        assert backend.apply_request(nouvelle) is True
        backend.stop()

    def test_changement_de_corrections_impose_un_rechargement(self, media_files):
        backend = self._backend(media_files["image"], MediaKind.IMAGE)
        backend.start()
        nouvelle = backend.request.with_(adjustments=ImageAdjustments(blur=5.0))
        assert backend.apply_request(nouvelle) is False
        backend.stop()


# --- Rendu video ------------------------------------------------------------
@pytest.mark.skipif(
    not VideoVlcBackend.is_available(), reason="libVLC absente de ce systeme"
)
class TestRenduVideo:
    def _backend(self, path, **kw):
        request = PlaybackRequest(path=str(path), kind=MediaKind.VIDEO, **kw)
        backend = VideoVlcBackend(request)
        backend.widget().resize(640, 360)
        return backend

    def test_lecture_video(self, media_files):
        if "video" not in media_files:
            pytest.skip("FFmpeg absent : pas de video de test")
        backend = self._backend(media_files["video"])
        assert backend.start() is True
        process(1200)
        assert backend.state == PlaybackState.PLAYING
        assert backend.position() is not None
        backend.stop()
        assert backend.state == PlaybackState.STOPPED

    def test_pause_et_reprise(self, media_files):
        if "video" not in media_files:
            pytest.skip("FFmpeg absent : pas de video de test")
        backend = self._backend(media_files["video"])
        backend.start()
        process(600)
        backend.pause()
        assert backend.state == PlaybackState.PAUSED
        backend.resume()
        assert backend.state == PlaybackState.PLAYING
        backend.stop()

    def test_fichier_manquant_signale_immediatement(self, media_files):
        backend = self._backend(media_files["absent"])
        assert backend.start() is False
        assert backend.error == "Fichier introuvable"

    def test_fichier_vide_signale(self, media_files):
        backend = self._backend(media_files["empty"])
        assert backend.start() is False
        assert "vide" in backend.error.lower()

    def test_fichier_corrompu_finit_par_etre_signale(self, media_files):
        """Un fichier illisible ne doit pas tourner en boucle silencieusement."""
        backend = self._backend(media_files["broken"])
        backend.start()
        # Le delai de garde verifie toutes les 1,5 s et abandonne apres 3 echecs.
        process(7000)
        assert backend.state == PlaybackState.ERROR, (
            "un fichier casse doit finir en erreur plutot que de boucler"
        )
        assert backend.error
        backend.stop()

    def test_volume_et_vitesse_sans_erreur(self, media_files):
        if "video" not in media_files:
            pytest.skip("FFmpeg absent : pas de video de test")
        backend = self._backend(media_files["video"], muted=False, volume=30)
        backend.start()
        process(500)
        backend.set_volume(70)
        backend.set_muted(True)
        backend.set_speed(1.5)
        backend.stop()


# --- Liberation des ressources ---------------------------------------------
class TestLiberationRessources:
    def test_arret_repete_est_sans_danger(self, media_files):
        request = PlaybackRequest(
            path=str(media_files["image"]), kind=MediaKind.IMAGE
        )
        backend = ImageBackend(request)
        backend.widget().resize(320, 180)
        backend.start()
        backend.stop()
        backend.stop()  # ne doit pas lever

    def test_cycles_repetes_ne_fuient_pas(self, media_files):
        """Vingt cycles d'ouverture/fermeture ne doivent rien laisser derriere."""
        import psutil, os

        process_info = psutil.Process(os.getpid())
        for _ in range(3):  # amorcage
            backend = ImageBackend(
                PlaybackRequest(path=str(media_files["gif"]),
                                kind=MediaKind.ANIMATED_IMAGE)
            )
            backend.widget().resize(320, 180)
            backend.start()
            backend.stop()
            backend.deleteLater()
        process(150)
        gc.collect()
        before = process_info.memory_info().rss

        for _ in range(20):
            backend = ImageBackend(
                PlaybackRequest(path=str(media_files["gif"]),
                                kind=MediaKind.ANIMATED_IMAGE)
            )
            backend.widget().resize(320, 180)
            backend.start()
            backend.stop()
            backend.deleteLater()
        process(200)
        gc.collect()
        after = process_info.memory_info().rss

        growth_mb = (after - before) / (1024 * 1024)
        assert growth_mb < 40, f"croissance memoire suspecte : {growth_mb:.1f} Mo"

    def test_arret_libere_les_images_de_l_animation(self, media_files):
        backend = ImageBackend(
            PlaybackRequest(path=str(media_files["gif"]),
                            kind=MediaKind.ANIMATED_IMAGE)
        )
        backend.widget().resize(320, 180)
        backend.start()
        assert backend._frames
        backend.stop()
        assert not backend._frames
        assert not backend._delays


# --- Analyse des medias -----------------------------------------------------
class TestAnalyseMedias:
    def test_image_fixe_reconnue(self, media_files):
        info = probe_media(media_files["image"])
        assert info.kind is MediaKind.IMAGE
        assert info.width == 640 and info.height == 360
        assert info.is_readable

    def test_gif_anime_reconnu_comme_anime(self, media_files):
        info = probe_media(media_files["gif"])
        assert info.kind is MediaKind.ANIMATED_IMAGE
        assert info.frame_count == 4
        assert info.duration and info.duration > 0

    def test_fichier_absent(self, media_files):
        info = probe_media(media_files["absent"])
        assert not info.is_readable
        assert "introuvable" in info.error.lower()

    def test_fichier_vide(self, media_files):
        info = probe_media(media_files["empty"])
        assert not info.is_readable
        assert info.size_bytes == 0

    def test_video_reelle(self, media_files):
        if "video" not in media_files:
            pytest.skip("FFmpeg absent : pas de video de test")
        info = probe_media(media_files["video"])
        assert info.kind is MediaKind.VIDEO
        assert info.width == 320 and info.height == 180
        assert info.duration and info.duration > 1
        assert info.fps and 10 < info.fps < 20

    def test_dossier_sans_index_html(self, tmp_path):
        folder = tmp_path / "pas_un_fond"
        folder.mkdir()
        info = probe_media(folder)
        assert not info.is_readable

    def test_dossier_avec_index_html(self, tmp_path):
        folder = tmp_path / "fond_web"
        folder.mkdir()
        (folder / "index.html").write_text("<html></html>", encoding="utf-8")
        info = probe_media(folder)
        assert info.kind is MediaKind.WEB
