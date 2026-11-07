"""Tests du service de planification, avec horloge simulee et moteur factice."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import List, Optional, Tuple

import pytest

from wallpaper_studio.data.database import ALL_DAYS_MASK, Database, days_mask_from_list
from wallpaper_studio.data.models import MediaItem, ScheduleRule
from wallpaper_studio.data.repositories import Repositories
from wallpaper_studio.media.types import MediaKind
from wallpaper_studio.scheduler.scheduler import SchedulerService

LUNDI = datetime(2026, 10, 19)
ECRAN_1 = "mon_ecran_1"
ECRAN_2 = "mon_ecran_2"


class HorlogeSimulee:
    """Horloge pilotee par les tests."""

    def __init__(self, start: datetime):
        self.now = start

    def __call__(self) -> datetime:
        return self.now

    def advance_to(self, moment: datetime) -> None:
        self.now = moment

    def advance(self, **kw) -> None:
        self.now = self.now + timedelta(**kw)


class MoteurFactice:
    """Enregistre les applications de fond, sans rien afficher."""

    def __init__(self):
        self.applied: List[Tuple[str, Optional[int], Optional[str]]] = []
        self.fail_next = False
        self.state = {}

    def __call__(self, monitor_key: str, media_id: Optional[int], rule) -> bool:
        if self.fail_next:
            self.fail_next = False
            return False
        self.applied.append((monitor_key, media_id, rule.name if rule else None))
        self.state[monitor_key] = media_id
        return True

    @property
    def count(self) -> int:
        return len(self.applied)


@pytest.fixture
def repos(tmp_path):
    return Repositories(Database(tmp_path / "test.db"))


@pytest.fixture
def medias(repos):
    """Trois fonds : jour, nuit, soir."""
    return {
        "jour": repos.media.add(
            MediaItem(path="C:/f/jour.mp4", title="Paysage jour", kind=MediaKind.VIDEO)
        ),
        "nuit": repos.media.add(
            MediaItem(path="C:/f/nuit.png", title="Nuit etoilee", kind=MediaKind.IMAGE)
        ),
        "soir": repos.media.add(
            MediaItem(path="C:/f/soir.gif", title="Soir", kind=MediaKind.ANIMATED_IMAGE)
        ),
    }


def ajoute_regle(repos, nom, debut_h, fin_h, media_id, **kw) -> int:
    return repos.schedule.add(
        ScheduleRule(
            name=nom,
            media_id=media_id,
            start_minute=int(debut_h * 60),
            end_minute=int(fin_h * 60),
            days_mask=kw.pop("days_mask", ALL_DAYS_MASK),
            monitor_key=kw.pop("monitor_key", None),
            priority=kw.pop("priority", 0),
            enabled=kw.pop("enabled", True),
        )
    )


def make_service(repos, clock, moteur, ecrans=(ECRAN_1,)):
    return SchedulerService(
        repos=repos,
        applier=moteur,
        monitor_keys_provider=lambda: list(ecrans),
        clock=clock,
    )


# --- Transitions jour / nuit ----------------------------------------------
class TestTransitionsJourNuit:
    def test_bascule_a_22h_puis_a_8h(self, repos, medias):
        ajoute_regle(repos, "Jour", 8, 22, medias["jour"])
        ajoute_regle(repos, "Nuit", 22, 8, medias["nuit"])
        clock = HorlogeSimulee(LUNDI.replace(hour=12))
        moteur = MoteurFactice()
        service = make_service(repos, clock, moteur)

        service.evaluate()
        assert moteur.state[ECRAN_1] == medias["jour"]

        clock.advance_to(LUNDI.replace(hour=22, minute=0))
        service.evaluate()
        assert moteur.state[ECRAN_1] == medias["nuit"]

        clock.advance_to(LUNDI.replace(hour=23, minute=30))
        service.evaluate()
        assert moteur.state[ECRAN_1] == medias["nuit"]

        # Lendemain 8h00 : retour au fond de jour.
        clock.advance_to((LUNDI + timedelta(days=1)).replace(hour=8))
        service.evaluate()
        assert moteur.state[ECRAN_1] == medias["jour"]

    def test_pas_de_reapplication_inutile(self, repos, medias):
        """Un fond deja affiche ne doit pas etre reapplique a chaque passe."""
        ajoute_regle(repos, "Jour", 8, 22, medias["jour"])
        clock = HorlogeSimulee(LUNDI.replace(hour=10))
        moteur = MoteurFactice()
        service = make_service(repos, clock, moteur)

        for minute in range(0, 50, 5):
            clock.advance_to(LUNDI.replace(hour=10, minute=minute))
            service.evaluate()

        assert moteur.count == 1

    def test_journee_complete_quatre_plages(self, repos, medias):
        ajoute_regle(repos, "Matin", 6, 12, medias["jour"])
        ajoute_regle(repos, "Apres-midi", 12, 18, medias["soir"])
        ajoute_regle(repos, "Soir", 18, 22, medias["jour"])
        ajoute_regle(repos, "Nuit", 22, 6, medias["nuit"])

        clock = HorlogeSimulee(LUNDI.replace(hour=0))
        moteur = MoteurFactice()
        service = make_service(repos, clock, moteur)

        # Simule 48 h, heure par heure.
        vus = []
        for h in range(48):
            clock.advance_to(LUNDI + timedelta(hours=h))
            service.evaluate()
            vus.append((h % 24, moteur.state[ECRAN_1]))

        attendu = {
            0: medias["nuit"], 5: medias["nuit"], 6: medias["jour"],
            11: medias["jour"], 12: medias["soir"], 17: medias["soir"],
            18: medias["jour"], 21: medias["jour"], 22: medias["nuit"],
        }
        for heure, media in attendu.items():
            observe = [m for h, m in vus if h == heure]
            assert all(o == media for o in observe), f"heure {heure}"

        # 1 application initiale (minuit, plage nocturne en cours) puis 4
        # bascules par jour sur 2 jours = 9 changements, sans aucun superflu.
        assert moteur.count == 9


# --- Plusieurs ecrans ------------------------------------------------------
class TestMultiEcrans:
    def test_programmes_independants_par_ecran(self, repos, medias):
        ajoute_regle(repos, "E1 jour", 8, 20, medias["jour"], monitor_key=ECRAN_1)
        ajoute_regle(repos, "E2 soir", 8, 20, medias["soir"], monitor_key=ECRAN_2)
        clock = HorlogeSimulee(LUNDI.replace(hour=12))
        moteur = MoteurFactice()
        service = make_service(repos, clock, moteur, ecrans=(ECRAN_1, ECRAN_2))

        service.evaluate()
        assert moteur.state[ECRAN_1] == medias["jour"]
        assert moteur.state[ECRAN_2] == medias["soir"]

    def test_debranchement_puis_rebranchement(self, repos, medias):
        ajoute_regle(repos, "Jour", 8, 20, medias["jour"])
        clock = HorlogeSimulee(LUNDI.replace(hour=12))
        moteur = MoteurFactice()
        ecrans = [ECRAN_1, ECRAN_2]
        service = SchedulerService(
            repos, moteur, lambda: list(ecrans), clock=clock
        )
        service.evaluate()
        assert moteur.count == 2

        # L'ecran 2 est debranche.
        ecrans.remove(ECRAN_2)
        service.notify_monitors_changed()
        service.evaluate()
        assert moteur.count == 2  # rien de neuf pour l'ecran 1

        # Rebranchement : son fond doit etre reapplique.
        ecrans.append(ECRAN_2)
        service.notify_monitors_changed()
        service.evaluate()
        assert moteur.count == 3
        assert moteur.applied[-1][0] == ECRAN_2

    def test_ecran_1_inchange_quand_ecran_2_bouge(self, repos, medias):
        """Le rebranchement d'un ecran ne doit pas perturber les autres."""
        ajoute_regle(repos, "E1", 0, 0, medias["jour"], monitor_key=ECRAN_1)
        ajoute_regle(repos, "E2", 0, 0, medias["nuit"], monitor_key=ECRAN_2)
        clock = HorlogeSimulee(LUNDI.replace(hour=12))
        moteur = MoteurFactice()
        ecrans = [ECRAN_1, ECRAN_2]
        service = SchedulerService(repos, moteur, lambda: list(ecrans), clock=clock)
        service.evaluate()

        ecrans.remove(ECRAN_2)
        service.notify_monitors_changed()
        service.evaluate()
        ecrans.append(ECRAN_2)
        service.notify_monitors_changed()
        service.evaluate()

        pour_ecran1 = [a for a in moteur.applied if a[0] == ECRAN_1]
        assert len(pour_ecran1) == 1


# --- Modes et suspension ---------------------------------------------------
class TestModes:
    def test_mode_manuel_n_applique_rien(self, repos, medias):
        ajoute_regle(repos, "Jour", 8, 22, medias["jour"])
        clock = HorlogeSimulee(LUNDI.replace(hour=12))
        moteur = MoteurFactice()
        service = make_service(repos, clock, moteur)

        service.set_enabled(False)
        service.evaluate()
        assert moteur.count == 0

        service.set_enabled(True)
        service.evaluate()
        assert moteur.count == 1

    def test_suspension_temporaire(self, repos, medias):
        ajoute_regle(repos, "Jour", 8, 22, medias["jour"])
        ajoute_regle(repos, "Nuit", 22, 8, medias["nuit"])
        clock = HorlogeSimulee(LUNDI.replace(hour=12))
        moteur = MoteurFactice()
        service = make_service(repos, clock, moteur)

        service.suspend_until(LUNDI.replace(hour=23))
        service.evaluate()
        assert moteur.count == 0
        assert service.is_suspended

        # Apres la fin de la suspension, la regle reprend.
        clock.advance_to(LUNDI.replace(hour=23, minute=1))
        service.evaluate()
        assert moteur.state[ECRAN_1] == medias["nuit"]

    def test_regle_desactivee_ignoree(self, repos, medias):
        rid = ajoute_regle(repos, "Jour", 8, 22, medias["jour"])
        repos.schedule.set_enabled(rid, False)
        clock = HorlogeSimulee(LUNDI.replace(hour=12))
        moteur = MoteurFactice()
        service = make_service(repos, clock, moteur)
        service.evaluate()
        assert moteur.count == 0


# --- Robustesse ------------------------------------------------------------
class TestRobustesse:
    def test_redemarrage_recalcule_l_etat_attendu(self, repos, medias):
        """Au demarrage, le fond attendu est applique sans attendre une bascule."""
        ajoute_regle(repos, "Nuit", 22, 8, medias["nuit"])
        clock = HorlogeSimulee(LUNDI.replace(hour=2))  # en pleine plage nocturne
        moteur = MoteurFactice()
        service = make_service(repos, clock, moteur)
        service.evaluate()
        assert moteur.state[ECRAN_1] == medias["nuit"]

    def test_sortie_de_veille_rattrape_la_transition_manquee(self, repos, medias):
        ajoute_regle(repos, "Jour", 8, 22, medias["jour"])
        ajoute_regle(repos, "Nuit", 22, 8, medias["nuit"])
        clock = HorlogeSimulee(LUNDI.replace(hour=20))
        moteur = MoteurFactice()
        service = make_service(repos, clock, moteur)
        service.evaluate()
        assert moteur.state[ECRAN_1] == medias["jour"]

        # Le PC dort de 20h a 23h : la bascule de 22h a ete manquee.
        clock.advance_to(LUNDI.replace(hour=23))
        service.notify_resume_from_sleep()
        service.evaluate()
        assert moteur.state[ECRAN_1] == medias["nuit"]

    def test_echec_d_application_est_reessaye(self, repos, medias):
        ajoute_regle(repos, "Jour", 8, 22, medias["jour"])
        clock = HorlogeSimulee(LUNDI.replace(hour=12))
        moteur = MoteurFactice()
        moteur.fail_next = True
        service = make_service(repos, clock, moteur)

        service.evaluate()
        assert moteur.count == 0  # l'echec n'est pas memorise

        service.evaluate()
        assert moteur.count == 1  # nouvelle tentative reussie

    def test_une_seule_boucle_concurrente(self, repos, medias):
        clock = HorlogeSimulee(LUNDI.replace(hour=12))
        service = make_service(repos, clock, MoteurFactice())
        try:
            assert service.start() is True
            assert service.start() is False  # deja en cours
            assert service.is_running
        finally:
            service.stop()
        assert not service.is_running

    def test_aucune_regle_ne_noircit_pas_l_ecran(self, repos, medias):
        """Sans regle active, le fond courant est laisse en place."""
        ajoute_regle(repos, "Matin", 6, 8, medias["jour"])
        clock = HorlogeSimulee(LUNDI.replace(hour=15))
        moteur = MoteurFactice()
        service = make_service(repos, clock, moteur)
        service.evaluate()
        assert moteur.count == 0

    def test_historique_enregistre_les_changements(self, repos, medias):
        ajoute_regle(repos, "Jour", 8, 22, medias["jour"])
        ajoute_regle(repos, "Nuit", 22, 8, medias["nuit"])
        clock = HorlogeSimulee(LUNDI.replace(hour=12))
        service = make_service(repos, clock, MoteurFactice())
        service.evaluate()
        clock.advance_to(LUNDI.replace(hour=22))
        service.evaluate()

        entrees = repos.history.list()
        assert len(entrees) == 2
        assert entrees[0].rule_name == "Nuit"
        assert entrees[0].media_title == "Nuit etoilee"
        assert entrees[0].reason == "planificateur"

    def test_prochaine_transition_annoncee(self, repos, medias):
        ajoute_regle(repos, "Jour", 8, 22, medias["jour"])
        ajoute_regle(repos, "Nuit", 22, 8, medias["nuit"])
        clock = HorlogeSimulee(LUNDI.replace(hour=20))
        service = make_service(repos, clock, MoteurFactice())
        service.evaluate()

        suivant = service.next_change()
        assert suivant is not None
        instant, etat = suivant
        assert instant == LUNDI.replace(hour=22)
        assert etat[ECRAN_1].media_id == medias["nuit"]
        assert "22:00" in service.describe_next()
