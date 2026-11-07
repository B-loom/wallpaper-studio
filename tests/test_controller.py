"""Tests d'integration du controleur : restauration, fermeture, multi-ecrans.

Le moteur est demarre pour de vrai mais les surfaces ne sont pas rattachees au
bureau : on verifie l'enchainement des composants, pas l'integration Windows.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from wallpaper_studio.data.models import MediaItem, ScheduleRule
from wallpaper_studio.media.types import FillMode, MediaKind

pytestmark = pytest.mark.usefixtures("qapp")


def process(ms: int = 60) -> None:
    from PySide6.QtCore import QEventLoop, QTimer
    from PySide6.QtWidgets import QApplication

    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()
    QApplication.processEvents()


@pytest.fixture
def controller(isolated_data, media_files):
    """Controleur complet branche sur des donnees temporaires."""
    from wallpaper_studio.app import AppController

    ctrl = AppController()
    yield ctrl
    try:
        ctrl.shutdown()
    except Exception:  # noqa: BLE001 - l'arret ne doit jamais casser un test
        pass


def add_media(controller, path, kind=MediaKind.IMAGE, title="Test") -> int:
    return controller.repos.media.add(
        MediaItem(path=str(path), title=title, kind=kind)
    )


class TestApplicationDesFonds:
    def test_appliquer_un_fond_sur_l_ecran_principal(self, controller, media_files):
        assert controller.engine.start() is True
        media_id = add_media(controller, media_files["image"])
        key = controller.monitors.primary().key

        assert controller.apply_media(key, media_id) is True
        state = controller.engine.state_for(key)
        assert state.backend is not None
        assert state.error is None
        assert controller.repos.monitors.get(key).media_id == media_id

    def test_fond_different_par_ecran(self, controller, media_files):
        """Chaque ecran recoit bien un media distinct.

        Avec un seul ecran physique, on verifie au moins que la cible est
        respectee ; avec plusieurs, que les contenus different reellement.
        """
        assert controller.engine.start() is True
        a = add_media(controller, media_files["image"], title="A")
        b = add_media(controller, media_files["gif"],
                      kind=MediaKind.ANIMATED_IMAGE, title="B")

        keys = [m.key for m in controller.monitors.monitors]
        controller.apply_media(keys[0], a)
        if len(keys) > 1:
            controller.apply_media(keys[1], b)
            assert (
                controller.engine.state_for(keys[0]).request.path
                != controller.engine.state_for(keys[1]).request.path
            )
            assert controller.repos.monitors.get(keys[1]).media_id == b
        assert controller.repos.monitors.get(keys[0]).media_id == a

    def test_media_inexistant_en_base_echoue_proprement(self, controller):
        controller.engine.start()
        key = controller.monitors.primary().key
        assert controller.apply_media(key, 9999) is False

    def test_fichier_manquant_remonte_une_erreur(self, controller, media_files):
        controller.engine.start()
        media_id = add_media(controller, media_files["absent"])
        key = controller.monitors.primary().key
        assert controller.apply_media(key, media_id) is False

    def test_retour_au_fond_precedent(self, controller, media_files):
        controller.engine.start()
        a = add_media(controller, media_files["image"], title="A")
        b = add_media(controller, media_files["gif"],
                      kind=MediaKind.ANIMATED_IMAGE, title="B")
        key = controller.monitors.primary().key

        controller.apply_media(key, a)
        controller.apply_media(key, b)
        assert controller.restore_previous(key) is True
        assert controller.repos.monitors.get(key).media_id == a

    def test_historique_enregistre_les_actions_manuelles(self, controller, media_files):
        controller.engine.start()
        media_id = add_media(controller, media_files["image"])
        key = controller.monitors.primary().key
        controller.apply_media(key, media_id, reason="manuel")

        entries = controller.repos.history.list()
        assert entries and entries[0].reason == "manuel"


class TestRedemarrage:
    def test_les_fonds_sont_restaures_au_demarrage(self, isolated_data, media_files):
        """Fermer puis rouvrir l'application doit retablir les fonds."""
        from wallpaper_studio.app import AppController

        first = AppController()
        first.engine.start()
        media_id = add_media(first, media_files["image"], title="Restaure")
        key = first.monitors.primary().key
        assert first.apply_media(key, media_id) is True
        first.shutdown()

        # Nouvelle instance : simule le redemarrage de l'application.
        second = AppController()
        try:
            assert second.engine.start() is True
            restored = second.restore_wallpapers()
            assert restored == 1
            state = second.engine.state_for(key)
            assert state is not None and state.backend is not None
            assert state.request.path == str(media_files["image"])
        finally:
            second.shutdown()

    def test_reglages_par_ecran_restaures(self, isolated_data, media_files):
        from wallpaper_studio.app import AppController

        first = AppController()
        first.engine.start()
        key = first.monitors.primary().key
        config = first.repos.monitors.get_or_create(key)
        config.fill_mode = FillMode.CONTAIN
        config.volume = 42
        config.muted = False
        first.repos.monitors.save(config)
        first.shutdown()

        second = AppController()
        try:
            restored = second.repos.monitors.get(key)
            assert restored.fill_mode is FillMode.CONTAIN
            assert restored.volume == 42
            assert restored.muted is False
        finally:
            second.shutdown()


class TestFenetreEtArrierePlan:
    def test_fermer_la_fenetre_n_arrete_ni_le_moteur_ni_le_planificateur(
        self, controller, media_files
    ):
        """Exigence : fermer la fenetre doit laisser le fond et les horaires actifs."""
        from wallpaper_studio.ui.main_window import MainWindow

        controller.start()
        media_id = add_media(controller, media_files["image"])
        key = controller.monitors.primary().key
        controller.apply_media(key, media_id)

        window = MainWindow(controller)
        window.show()
        process(120)

        assert controller.settings.get("fermer_vers_zone_notification") is True
        window.close()
        process(120)

        assert window.isVisible() is False, "la fenetre doit etre masquee"
        assert controller.scheduler.is_running, (
            "le planificateur doit continuer apres la fermeture de la fenetre"
        )
        state = controller.engine.state_for(key)
        assert state.backend is not None, "le fond doit rester actif"
        assert state.backend.state == "playing"

        window.force_quit()

    def test_arret_complet_libere_tout(self, controller, media_files):
        controller.start()
        media_id = add_media(controller, media_files["gif"],
                             kind=MediaKind.ANIMATED_IMAGE)
        key = controller.monitors.primary().key
        controller.apply_media(key, media_id)
        assert controller.engine.active_count == 1

        controller.shutdown()
        assert controller.scheduler.is_running is False
        assert controller.engine.screens == {}

    def test_pause_globale_et_reprise(self, controller, media_files):
        controller.engine.start()
        media_id = add_media(controller, media_files["gif"],
                             kind=MediaKind.ANIMATED_IMAGE)
        key = controller.monitors.primary().key
        controller.apply_media(key, media_id)

        controller.engine.pause_all("test")
        assert controller.engine.is_paused
        assert controller.engine.state_for(key).paused

        controller.engine.resume_all("test")
        assert not controller.engine.is_paused
        assert not controller.engine.state_for(key).paused


class TestPlanificationIntegree:
    def test_le_planificateur_applique_un_fond_de_bout_en_bout(
        self, controller, media_files
    ):
        """Du calcul de la regle jusqu'au rendu effectif."""
        controller.engine.start()
        media_id = add_media(controller, media_files["image"], title="Programme")
        key = controller.monitors.primary().key

        # Regle couvrant les 24 heures : active quelle que soit l'heure du test.
        controller.repos.schedule.add(
            ScheduleRule(name="Permanent", media_id=media_id,
                         start_minute=0, end_minute=0)
        )

        controller.scheduler.evaluate()
        process(200)  # laisse le signal en file d'attente arriver

        state = controller.engine.state_for(key)
        assert state is not None and state.backend is not None
        assert state.request.path == str(media_files["image"])

    def test_reglages_de_la_regle_priment_sur_ceux_de_l_ecran(
        self, controller, media_files
    ):
        controller.engine.start()
        media_id = add_media(controller, media_files["image"])
        key = controller.monitors.primary().key

        config = controller.repos.monitors.get_or_create(key)
        config.fill_mode = FillMode.CENTER
        controller.repos.monitors.save(config)

        rule = ScheduleRule(name="R", media_id=media_id, start_minute=0,
                            end_minute=0, fill_mode=FillMode.CONTAIN)
        request = controller.build_request(key, media_id, rule=rule)
        assert request.fill_mode is FillMode.CONTAIN

    def test_choix_manuel_reapplique_apres_coup_par_le_planificateur(
        self, controller, media_files
    ):
        """Le planificateur doit pouvoir reprendre la main a la transition suivante."""
        controller.engine.start()
        auto = add_media(controller, media_files["image"], title="Auto")
        manuel = add_media(controller, media_files["gif"],
                           kind=MediaKind.ANIMATED_IMAGE, title="Manuel")
        key = controller.monitors.primary().key

        controller.repos.schedule.add(
            ScheduleRule(name="Permanent", media_id=auto,
                         start_minute=0, end_minute=0)
        )
        controller.scheduler.evaluate()
        process(150)

        # L'utilisateur choisit autre chose a la main.
        controller.apply_media(key, manuel, reason="manuel")
        assert controller.engine.state_for(key).request.path == str(media_files["gif"])

        # La passe suivante du planificateur remet le fond programme.
        controller.scheduler.evaluate()
        process(150)
        assert controller.engine.state_for(key).request.path == str(media_files["image"])
