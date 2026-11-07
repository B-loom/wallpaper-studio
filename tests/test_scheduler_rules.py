"""Tests de la logique des regles horaires, avec horloge simulee."""

from __future__ import annotations

from datetime import datetime

import pytest

from wallpaper_studio.data.database import ALL_DAYS_MASK, days_mask_from_list
from wallpaper_studio.data.models import ScheduleRule
from wallpaper_studio.scheduler.rules import (
    ConflictPolicy,
    describe_transition,
    next_transition,
    resolve_all,
    resolve_rule,
    rule_is_active,
    rule_started_at,
    validate_rule,
)

ECRAN_1 = "mon_ecran_1"
ECRAN_2 = "mon_ecran_2"

# Lundi 2026-10-19 sert de reference dans tous les tests.
LUNDI = datetime(2026, 10, 19)
MARDI = datetime(2026, 10, 20)
SAMEDI = datetime(2026, 10, 24)


def at(day: datetime, hour: int, minute: int = 0) -> datetime:
    return day.replace(hour=hour, minute=minute)


def make_rule(
    rid: int, name: str, start_h: float, end_h: float, media_id: int, **kw
) -> ScheduleRule:
    return ScheduleRule(
        id=rid,
        name=name,
        media_id=media_id,
        start_minute=int(start_h * 60),
        end_minute=int(end_h * 60),
        days_mask=kw.pop("days_mask", ALL_DAYS_MASK),
        monitor_key=kw.pop("monitor_key", None),
        priority=kw.pop("priority", 0),
        enabled=kw.pop("enabled", True),
        **kw,
    )


# --- Plage simple ----------------------------------------------------------
class TestPlageSimple:
    def setup_method(self):
        self.jour = make_rule(1, "Jour", 8, 22, media_id=10)

    @pytest.mark.parametrize("heure", [8, 9, 12, 18, 21])
    def test_actif_pendant_la_plage(self, heure):
        assert rule_is_active(self.jour, at(LUNDI, heure))

    @pytest.mark.parametrize("heure", [0, 7, 22, 23])
    def test_inactif_hors_plage(self, heure):
        assert not rule_is_active(self.jour, at(LUNDI, heure))

    def test_borne_de_debut_incluse(self):
        assert rule_is_active(self.jour, at(LUNDI, 8, 0))

    def test_borne_de_fin_exclue(self):
        """22h00 appartient a la plage suivante, pas a celle qui se termine."""
        assert not rule_is_active(self.jour, at(LUNDI, 22, 0))
        assert rule_is_active(self.jour, at(LUNDI, 21, 59))

    def test_regle_desactivee_jamais_active(self):
        self.jour.enabled = False
        assert not rule_is_active(self.jour, at(LUNDI, 12))


# --- Plage traversant minuit ----------------------------------------------
class TestPlageNocturne:
    def setup_method(self):
        self.nuit = make_rule(2, "Nuit", 22, 8, media_id=20)

    @pytest.mark.parametrize("heure", [22, 23])
    def test_actif_en_soiree(self, heure):
        assert rule_is_active(self.nuit, at(LUNDI, heure))

    @pytest.mark.parametrize("heure", [0, 3, 7])
    def test_actif_au_petit_matin(self, heure):
        assert rule_is_active(self.nuit, at(MARDI, heure))

    @pytest.mark.parametrize("heure", [8, 12, 21])
    def test_inactif_en_journee(self, heure):
        assert not rule_is_active(self.nuit, at(LUNDI, heure))

    def test_plage_continue_sans_trou(self):
        """La bascule a 22h00 pile doit basculer sur la nuit."""
        assert rule_is_active(self.nuit, at(LUNDI, 22, 0))
        assert not rule_is_active(self.nuit, at(LUNDI, 7, 59) .replace(hour=21, minute=59))

    def test_debut_de_plage_veille_au_petit_matin(self):
        """A 3h du matin mardi, la plage a commence lundi a 22h."""
        debut = rule_started_at(self.nuit, at(MARDI, 3))
        assert debut == at(LUNDI, 22, 0)

    def test_debut_de_plage_le_soir_meme(self):
        debut = rule_started_at(self.nuit, at(LUNDI, 23))
        assert debut == at(LUNDI, 22, 0)

    def test_masque_de_jours_designe_le_jour_de_debut(self):
        """Nuit cochee lundi seulement : active lundi 23h et mardi 3h."""
        self.nuit.days_mask = days_mask_from_list([0])  # lundi
        assert rule_is_active(self.nuit, at(LUNDI, 23))
        assert rule_is_active(self.nuit, at(MARDI, 3))
        # Mardi soir n'est pas couvert (mardi non coche).
        assert not rule_is_active(self.nuit, at(MARDI, 23))

    def test_plage_24h_quand_debut_egale_fin(self):
        continue_ = make_rule(3, "Continu", 0, 0, media_id=30)
        for heure in (0, 6, 13, 23):
            assert rule_is_active(continue_, at(LUNDI, heure))


# --- Jours de la semaine ---------------------------------------------------
class TestJoursSemaine:
    def test_jours_ouvres(self):
        regle = make_rule(
            4, "Bureau", 9, 18, media_id=40, days_mask=days_mask_from_list([0, 1, 2, 3, 4])
        )
        assert rule_is_active(regle, at(LUNDI, 10))
        assert not rule_is_active(regle, at(SAMEDI, 10))

    def test_week_end(self):
        regle = make_rule(
            5, "Week-end", 9, 18, media_id=50, days_mask=days_mask_from_list([5, 6])
        )
        assert rule_is_active(regle, at(SAMEDI, 10))
        assert not rule_is_active(regle, at(LUNDI, 10))


# --- Resolution et conflits ------------------------------------------------
class TestResolutionConflits:
    def test_jour_nuit_se_relaient(self):
        jour = make_rule(1, "Jour", 8, 22, media_id=10)
        nuit = make_rule(2, "Nuit", 22, 8, media_id=20)
        regles = [jour, nuit]
        assert resolve_rule(regles, ECRAN_1, at(LUNDI, 12)).media_id == 10
        assert resolve_rule(regles, ECRAN_1, at(LUNDI, 23)).media_id == 20
        assert resolve_rule(regles, ECRAN_1, at(MARDI, 3)).media_id == 20
        assert resolve_rule(regles, ECRAN_1, at(MARDI, 9)).media_id == 10

    def test_aucune_regle_retourne_none(self):
        regle = make_rule(1, "Matin", 8, 10, media_id=10)
        assert resolve_rule([regle], ECRAN_1, at(LUNDI, 15)) is None

    def test_priorite_la_plus_elevee_gagne(self):
        base = make_rule(1, "Base", 8, 22, media_id=10, priority=0)
        special = make_rule(2, "Special", 10, 12, media_id=99, priority=5)
        got = resolve_rule([base, special], ECRAN_1, at(LUNDI, 11))
        assert got.media_id == 99

    def test_regle_par_ecran_prime_sur_regle_globale(self):
        globale = make_rule(1, "Tous", 8, 22, media_id=10)
        ciblee = make_rule(2, "Ecran 1", 8, 22, media_id=77, monitor_key=ECRAN_1)
        assert resolve_rule([globale, ciblee], ECRAN_1, at(LUNDI, 12)).media_id == 77
        # L'ecran 2 n'est pas concerne par la regle ciblee.
        assert resolve_rule([globale, ciblee], ECRAN_2, at(LUNDI, 12)).media_id == 10

    def test_politique_plage_la_plus_courte(self):
        large = make_rule(1, "Large", 8, 22, media_id=10)
        courte = make_rule(2, "Courte", 10, 11, media_id=99)
        got = resolve_rule(
            [large, courte], ECRAN_1, at(LUNDI, 10, 30), ConflictPolicy.SHORTEST
        )
        assert got.media_id == 99

    def test_politique_plus_recemment_commencee(self):
        tot = make_rule(1, "Tot", 8, 20, media_id=10)
        tard = make_rule(2, "Tard", 14, 20, media_id=99)
        got = resolve_rule(
            [tot, tard], ECRAN_1, at(LUNDI, 15), ConflictPolicy.MOST_RECENT
        )
        assert got.media_id == 99

    def test_ecrans_independants(self):
        r1 = make_rule(1, "E1", 8, 22, media_id=11, monitor_key=ECRAN_1)
        r2 = make_rule(2, "E2", 8, 22, media_id=22, monitor_key=ECRAN_2)
        etats = resolve_all([r1, r2], [ECRAN_1, ECRAN_2], at(LUNDI, 12))
        assert etats[ECRAN_1].media_id == 11
        assert etats[ECRAN_2].media_id == 22


# --- Prochaine transition --------------------------------------------------
class TestProchaineTransition:
    def setup_method(self):
        self.regles = [
            make_rule(1, "Jour", 8, 22, media_id=10),
            make_rule(2, "Nuit", 22, 8, media_id=20),
        ]

    def test_transition_du_soir(self):
        instant, etat = next_transition(self.regles, [ECRAN_1], at(LUNDI, 20))
        assert instant == at(LUNDI, 22, 0)
        assert etat[ECRAN_1].media_id == 20

    def test_transition_du_matin(self):
        instant, etat = next_transition(self.regles, [ECRAN_1], at(MARDI, 3))
        assert instant == at(MARDI, 8, 0)
        assert etat[ECRAN_1].media_id == 10

    def test_transition_juste_avant_la_bascule(self):
        instant, _ = next_transition(self.regles, [ECRAN_1], at(LUNDI, 21, 59))
        assert instant == at(LUNDI, 22, 0)

    def test_quatre_plages_dans_la_journee(self):
        regles = [
            make_rule(1, "Matin", 8, 12, media_id=1),
            make_rule(2, "Apres-midi", 12, 18, media_id=2),
            make_rule(3, "Soir", 18, 22, media_id=3),
            make_rule(4, "Nuit", 22, 8, media_id=4),
        ]
        attendus = [
            (at(LUNDI, 9), at(LUNDI, 12), 2),
            (at(LUNDI, 13), at(LUNDI, 18), 3),
            (at(LUNDI, 19), at(LUNDI, 22), 4),
            (at(LUNDI, 23), at(MARDI, 8), 1),
        ]
        for depart, instant_attendu, media_attendu in attendus:
            instant, etat = next_transition(regles, [ECRAN_1], depart)
            assert instant == instant_attendu
            assert etat[ECRAN_1].media_id == media_attendu

    def test_aucune_transition_si_une_seule_regle_permanente(self):
        regle = make_rule(1, "Toujours", 0, 0, media_id=10)
        assert next_transition([regle], [ECRAN_1], at(LUNDI, 12)) is None

    def test_transition_hebdomadaire(self):
        """Une regle du week-end declenche bien une transition future."""
        semaine = make_rule(
            1, "Semaine", 0, 0, media_id=10, days_mask=days_mask_from_list([0, 1, 2, 3, 4])
        )
        weekend = make_rule(
            2, "Week-end", 0, 0, media_id=20, days_mask=days_mask_from_list([5, 6])
        )
        instant, etat = next_transition([semaine, weekend], [ECRAN_1], at(LUNDI, 12))
        assert instant == SAMEDI.replace(hour=0, minute=0)
        assert etat[ECRAN_1].media_id == 20


# --- Validation ------------------------------------------------------------
class TestValidation:
    def test_regle_valide(self):
        assert validate_rule(make_rule(1, "Jour", 8, 22, media_id=10)) == []

    def test_nom_obligatoire(self):
        assert validate_rule(make_rule(1, "", 8, 22, media_id=10))

    def test_media_obligatoire(self):
        assert validate_rule(make_rule(1, "Jour", 8, 22, media_id=0))

    def test_au_moins_un_jour(self):
        assert validate_rule(make_rule(1, "Jour", 8, 22, media_id=10, days_mask=0))


def test_description_du_delai():
    base = at(LUNDI, 20)
    assert "2 h" in describe_transition(base, at(LUNDI, 22))
    assert "min" in describe_transition(base, at(LUNDI, 20, 30))
