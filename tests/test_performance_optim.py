"""Tests des optimisations de memoire et de processeur.

Ces tests verrouillent les comportements qui font la frugalite du logiciel :
une page d'interface non consultee ne doit pas exister, les minuteurs doivent
s'arreter quand la fenetre est masquee, et libVLC doit etre rendue au systeme
des qu'aucune video n'est affichee.
"""

from __future__ import annotations

import time

import pytest

from wallpaper_studio.data.models import MediaItem
from wallpaper_studio.media.types import MediaKind

pytestmark = pytest.mark.usefixtures("qapp")


def pump(seconds: float = 0.15) -> None:
    from PySide6.QtWidgets import QApplication

    deadline = time.time() + seconds
    while time.time() < deadline:
        QApplication.processEvents()
        time.sleep(0.01)


@pytest.fixture
def controller(isolated_data):
    from wallpaper_studio.app import AppController

    ctrl = AppController()
    yield ctrl
    try:
        ctrl.shutdown()
    except Exception:  # noqa: BLE001
        pass


# --- Creation paresseuse des pages -----------------------------------------
class TestPagesParesseuses:
    def test_seule_la_page_accueil_existe_au_demarrage(self, controller):
        from wallpaper_studio.ui.main_window import MainWindow

        window = MainWindow(controller)
        try:
            assert set(window._pages) == {"home"}, (
                "aucune page autre que l'accueil ne doit etre construite"
            )
        finally:
            window.release()
            window.deleteLater()

    def test_une_page_est_construite_a_sa_premiere_ouverture(self, controller):
        from wallpaper_studio.ui.main_window import MainWindow

        window = MainWindow(controller)
        try:
            assert "library" not in window._pages
            window.show_page("library")
            assert "library" in window._pages
            # Les autres restent absentes.
            assert "editor" not in window._pages
            assert "performance" not in window._pages
        finally:
            window.release()
            window.deleteLater()

    def test_une_page_n_est_construite_qu_une_fois(self, controller):
        from wallpaper_studio.ui.main_window import MainWindow

        window = MainWindow(controller)
        try:
            window.show_page("history")
            premiere = window._pages["history"]
            window.show_page("home")
            window.show_page("history")
            assert window._pages["history"] is premiere
        finally:
            window.release()
            window.deleteLater()

    def test_toutes_les_pages_restent_constructibles(self, controller):
        from wallpaper_studio.ui.main_window import MainWindow, PAGES

        window = MainWindow(controller)
        try:
            for key, _, _ in PAGES:
                window.show_page(key)
                assert key in window._pages, f"page {key} non construite"
            assert len(window._pages) == len(PAGES)
        finally:
            window.release()
            window.deleteLater()


# --- Gel de l'interface -----------------------------------------------------
class TestGelInterface:
    def test_les_minuteurs_s_arretent_quand_la_fenetre_est_masquee(self, controller):
        from wallpaper_studio.ui.main_window import MainWindow

        window = MainWindow(controller)
        window.show()
        pump(0.2)
        try:
            accueil = window._pages["home"]
            assert accueil._tick.isActive()

            window.hide()
            pump(0.2)
            assert not accueil._tick.isActive(), (
                "le minuteur de l'accueil doit s'arreter quand la fenetre est masquee"
            )

            window.show()
            pump(0.2)
            assert accueil._tick.isActive()
        finally:
            window.release()
            window.deleteLater()

    def test_le_releve_de_performances_ne_tourne_pas_sans_sa_page(self, controller):
        perf = controller.perf
        perf.start()
        try:
            assert not perf._measure.isActive(), (
                "psutil ne doit pas etre interroge tant que la page "
                "Performances n'est pas ouverte"
            )
            perf.set_measuring(True)
            assert perf._measure.isActive()
            perf.set_measuring(False)
            assert not perf._measure.isActive()
        finally:
            perf.stop()

    def test_la_surveillance_ralentit_en_arriere_plan(self, controller):
        from wallpaper_studio.perf.performance_manager import (
            WATCH_INTERVAL_HIDDEN,
            WATCH_INTERVAL_VISIBLE,
        )

        perf = controller.perf
        perf.set_ui_visible(True)
        assert perf._watch.interval() == WATCH_INTERVAL_VISIBLE
        perf.set_ui_visible(False)
        assert perf._watch.interval() == WATCH_INTERVAL_HIDDEN


# --- Liberation de libVLC ---------------------------------------------------
class TestLiberationVlc:
    def test_vlc_est_liberee_sans_video_affichee(self, controller, media_files):
        from wallpaper_studio.engine.backends import vlc_runtime
        from wallpaper_studio.engine.backends.video_vlc import VideoVlcBackend

        if "video" not in media_files or not VideoVlcBackend.is_available():
            pytest.skip("libVLC ou FFmpeg absent")

        controller.engine.start()
        key = controller.monitors.primary().key

        video_id = controller.repos.media.add(
            MediaItem(path=str(media_files["video"]), title="v",
                      kind=MediaKind.VIDEO)
        )
        assert controller.apply_media(key, video_id)
        pump(0.6)
        assert vlc_runtime.instance_is_loaded()

        # Le remplacement par une image doit rendre la memoire de libVLC.
        image_id = controller.repos.media.add(
            MediaItem(path=str(media_files["image"]), title="i",
                      kind=MediaKind.IMAGE)
        )
        assert controller.apply_media(key, image_id)
        pump(0.3)

        controller.engine._release_vlc_if_idle()
        assert not vlc_runtime.instance_is_loaded(), (
            "libVLC doit etre liberee quand plus aucune video n'est affichee"
        )

    def test_vlc_reste_chargee_tant_qu_une_video_joue(self, controller, media_files):
        from wallpaper_studio.engine.backends import vlc_runtime
        from wallpaper_studio.engine.backends.video_vlc import VideoVlcBackend

        if "video" not in media_files or not VideoVlcBackend.is_available():
            pytest.skip("libVLC ou FFmpeg absent")

        controller.engine.start()
        key = controller.monitors.primary().key
        video_id = controller.repos.media.add(
            MediaItem(path=str(media_files["video"]), title="v",
                      kind=MediaKind.VIDEO)
        )
        assert controller.apply_media(key, video_id), (
            "la video de test n'a pas pu etre appliquee"
        )
        pump(0.6)
        assert controller.engine._video_backends_active(), (
            "le moteur video devrait etre actif apres application d'une video"
        )

        controller.engine._release_vlc_if_idle()
        assert vlc_runtime.instance_is_loaded(), (
            "libVLC ne doit pas etre liberee pendant une lecture"
        )

    def test_media_muet_desactive_la_sortie_audio(self, media_files):
        """Un fond muet ne doit pas ouvrir de pipeline audio."""
        from wallpaper_studio.engine.backends.video_vlc import VideoVlcBackend
        from wallpaper_studio.engine.playback import PlaybackRequest

        if "video" not in media_files or not VideoVlcBackend.is_available():
            pytest.skip("libVLC ou FFmpeg absent")

        backend = VideoVlcBackend(
            PlaybackRequest(path=str(media_files["video"]), kind=MediaKind.VIDEO,
                            muted=True, volume=0)
        )
        backend.widget().resize(320, 180)
        assert backend.start()
        pump(0.5)
        try:
            assert backend.state == "playing"
        finally:
            backend.stop()


# --- Restitution de la memoire ---------------------------------------------
class TestRestitutionMemoire:
    def test_trim_ne_leve_pas_et_mesure(self):
        from wallpaper_studio.system.memory import current_rss_mb, trim_working_set

        avant = current_rss_mb()
        assert avant is None or avant > 0
        # La valeur peut etre None si psutil manque ; l'appel ne doit jamais lever.
        trim_working_set("test")

    def test_l_application_reste_utilisable_apres_un_trim(self, controller,
                                                          media_files):
        from wallpaper_studio.system.memory import trim_working_set

        controller.engine.start()
        key = controller.monitors.primary().key
        media_id = controller.repos.media.add(
            MediaItem(path=str(media_files["image"]), title="i",
                      kind=MediaKind.IMAGE)
        )
        assert controller.apply_media(key, media_id)
        trim_working_set("test")
        pump(0.2)
        # Le fond doit toujours etre en lecture apres restitution de memoire.
        state = controller.engine.state_for(key)
        assert state.backend is not None
        assert state.backend.state == "playing"
