"""Persistance : reglages, bibliotheque, ecrans et redemarrage de l'application."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from wallpaper_studio.data.database import Database
from wallpaper_studio.data.models import MediaItem, ScheduleRule
from wallpaper_studio.data.repositories import Repositories
from wallpaper_studio.data.settings import Settings
from wallpaper_studio.engine.playback import EffectConfig, ImageAdjustments
from wallpaper_studio.media.types import FillMode, MediaKind


# --- Reglages ---------------------------------------------------------------
class TestReglages:
    def test_valeurs_par_defaut_ecrites_au_premier_lancement(self, tmp_path):
        path = tmp_path / "reglages.json"
        settings = Settings(path=path)
        assert path.exists()
        assert settings.get("langue") == "fr"
        assert settings.get("theme") == "sombre"

    def test_persistance_apres_redemarrage(self, tmp_path):
        path = tmp_path / "reglages.json"
        first = Settings(path=path)
        first.set("limite_fps", 24)
        first.set("pause_si_batterie", False)
        first.set("theme", "clair")

        # Nouvelle instance : simule un redemarrage de l'application.
        second = Settings(path=path)
        assert second.get("limite_fps") == 24
        assert second.get("pause_si_batterie") is False
        assert second.get("theme") == "clair"

    def test_cle_inconnue_du_fichier_est_ignoree(self, tmp_path):
        path = tmp_path / "reglages.json"
        path.write_text(json.dumps({"limite_fps": 45, "cle_inventee": 1}), encoding="utf-8")
        settings = Settings(path=path)
        assert settings.get("limite_fps") == 45
        assert "cle_inventee" not in settings.as_dict()

    def test_nouvelle_cle_prend_sa_valeur_par_defaut(self, tmp_path):
        """Un fichier ecrit par une version anterieure reste utilisable."""
        path = tmp_path / "reglages.json"
        path.write_text(json.dumps({"limite_fps": 45}), encoding="utf-8")
        settings = Settings(path=path)
        assert settings.get("qualite") == "equilibre"

    def test_fichier_corrompu_retombe_sur_les_defauts(self, tmp_path):
        path = tmp_path / "reglages.json"
        path.write_text("{ceci n'est pas du JSON", encoding="utf-8")
        settings = Settings(path=path)
        assert settings.get("limite_fps") == 30
        # L'original est conserve pour diagnostic.
        assert path.with_suffix(".json.corrompu").exists()

    def test_export_puis_import(self, tmp_path):
        source = Settings(path=tmp_path / "a.json")
        source.set("limite_fps", 17)
        source.set("qualite", "qualite")
        export = source.export_to(tmp_path / "sauvegarde.json")

        target = Settings(path=tmp_path / "b.json")
        assert target.get("limite_fps") == 30
        assert target.import_from(export) is True
        assert target.get("limite_fps") == 17
        assert target.get("qualite") == "qualite"

    def test_import_d_un_fichier_invalide_echoue_proprement(self, tmp_path):
        settings = Settings(path=tmp_path / "a.json")
        mauvais = tmp_path / "mauvais.json"
        mauvais.write_text("pas du json", encoding="utf-8")
        assert settings.import_from(mauvais) is False
        assert settings.get("limite_fps") == 30

    def test_reinitialisation(self, tmp_path):
        settings = Settings(path=tmp_path / "a.json")
        settings.set("limite_fps", 12)
        settings.reset()
        assert settings.get("limite_fps") == 30
        assert Settings(path=tmp_path / "a.json").get("limite_fps") == 30

    def test_ecriture_atomique_ne_laisse_pas_de_fichier_temporaire(self, tmp_path):
        settings = Settings(path=tmp_path / "a.json")
        settings.set("limite_fps", 33)
        assert list(tmp_path.glob("*.tmp")) == []


# --- Base de donnees --------------------------------------------------------
class TestBaseDeDonnees:
    def test_etat_des_ecrans_survit_au_redemarrage(self, tmp_path):
        path = tmp_path / "test.db"
        first = Repositories(Database(path))
        media_id = first.media.add(
            MediaItem(path="C:/f/a.png", title="A", kind=MediaKind.IMAGE)
        )
        config = first.monitors.get_or_create("ecran_1", "\\\\.\\DISPLAY1", "Ecran")
        config.fill_mode = FillMode.CONTAIN
        config.volume = 55
        config.muted = False
        config.speed = 1.5
        config.adjustments = ImageAdjustments(brightness=1.3, blur=2.0)
        config.effects = [EffectConfig("neige", True, 0.7)]
        first.monitors.save(config)
        first.monitors.set_media("ecran_1", media_id)
        first.close()

        second = Repositories(Database(path))
        restored = second.monitors.get("ecran_1")
        assert restored is not None
        assert restored.media_id == media_id
        assert restored.fill_mode is FillMode.CONTAIN
        assert restored.volume == 55
        assert restored.muted is False
        assert restored.speed == pytest.approx(1.5)
        assert restored.adjustments.brightness == pytest.approx(1.3)
        assert restored.adjustments.blur == pytest.approx(2.0)
        assert len(restored.effects) == 1
        assert restored.effects[0].name == "neige"

    def test_regles_horaires_survivent_au_redemarrage(self, tmp_path):
        path = tmp_path / "test.db"
        first = Repositories(Database(path))
        media_id = first.media.add(
            MediaItem(path="C:/f/n.png", title="Nuit", kind=MediaKind.IMAGE)
        )
        first.schedule.add(
            ScheduleRule(name="Nuit", media_id=media_id,
                         start_minute=22 * 60, end_minute=8 * 60, priority=3)
        )
        first.close()

        second = Repositories(Database(path))
        rules = second.schedule.list()
        assert len(rules) == 1
        assert rules[0].name == "Nuit"
        assert rules[0].crosses_midnight
        assert rules[0].priority == 3
        assert rules[0].media_title == "Nuit"

    def test_fond_precedent_memorise(self, tmp_path):
        repos = Repositories(Database(tmp_path / "t.db"))
        a = repos.media.add(MediaItem(path="C:/a.png", title="A", kind=MediaKind.IMAGE))
        b = repos.media.add(MediaItem(path="C:/b.png", title="B", kind=MediaKind.IMAGE))
        repos.monitors.set_media("e1", a)
        repos.monitors.set_media("e1", b)
        config = repos.monitors.get("e1")
        assert config.media_id == b
        assert config.previous_media_id == a

    def test_sauvegarde_de_la_base_est_relisible(self, tmp_path):
        repos = Repositories(Database(tmp_path / "t.db"))
        repos.media.add(MediaItem(path="C:/a.png", title="A", kind=MediaKind.IMAGE))
        backup = repos.db.backup_to(tmp_path / "sauvegarde.db")

        restored = Repositories(Database(backup))
        assert restored.media.count() == 1
        assert restored.media.list()[0].title == "A"

    def test_suppression_d_un_media_supprime_ses_regles(self, tmp_path):
        repos = Repositories(Database(tmp_path / "t.db"))
        media_id = repos.media.add(
            MediaItem(path="C:/a.png", title="A", kind=MediaKind.IMAGE)
        )
        repos.schedule.add(
            ScheduleRule(name="R", media_id=media_id, start_minute=0, end_minute=600)
        )
        repos.media.remove(media_id)
        assert repos.schedule.count() == 0

    def test_base_plus_recente_est_refusee(self, tmp_path):
        path = tmp_path / "futur.db"
        Repositories(Database(path)).close()
        import sqlite3

        conn = sqlite3.connect(str(path))
        conn.execute("PRAGMA user_version = 99")
        conn.commit()
        conn.close()

        with pytest.raises(RuntimeError, match="plus recente"):
            Database(path)

    def test_historique_limite_sa_taille(self, tmp_path):
        from wallpaper_studio.data.models import HistoryEntry

        repos = Repositories(Database(tmp_path / "t.db"))
        for i in range(60):
            repos.history.add(
                HistoryEntry(monitor_key="e1", media_title=f"#{i}", reason="manuel")
            )
        repos.history.prune(keep=20)
        assert len(repos.history.list(limit=500)) == 20


# --- Bibliotheque -----------------------------------------------------------
class TestBibliotheque:
    def test_fichiers_manquants_detectes(self, tmp_path, repos):
        present = tmp_path / "present.png"
        present.write_bytes(b"x")
        repos.media.add(
            MediaItem(path=str(present), title="Present", kind=MediaKind.IMAGE)
        )
        repos.media.add(
            MediaItem(path=str(tmp_path / "absent.png"), title="Absent",
                      kind=MediaKind.IMAGE)
        )

        missing = repos.media.refresh_missing_flags()
        assert len(missing) == 1
        assert missing[0].title == "Absent"
        assert repos.media.count_missing() == 1

        # Le fichier revient : l'indicateur doit se lever.
        (tmp_path / "absent.png").write_bytes(b"x")
        assert repos.media.refresh_missing_flags() == []
        assert repos.media.count_missing() == 0

    def test_retrait_sans_suppression_du_fichier(self, tmp_path, repos):
        source = tmp_path / "garde.png"
        source.write_bytes(b"x")
        media_id = repos.media.add(
            MediaItem(path=str(source), title="Garde", kind=MediaKind.IMAGE)
        )
        repos.media.remove(media_id, delete_file=False)
        assert repos.media.count() == 0
        assert source.exists(), "le fichier d'origine ne doit pas etre efface"

    def test_suppression_explicite_du_fichier(self, tmp_path, repos):
        source = tmp_path / "jette.png"
        source.write_bytes(b"x")
        media_id = repos.media.add(
            MediaItem(path=str(source), title="Jette", kind=MediaKind.IMAGE)
        )
        repos.media.remove(media_id, delete_file=True)
        assert not source.exists()

    def test_import_du_meme_chemin_ne_duplique_pas(self, repos):
        first = repos.media.add(
            MediaItem(path="C:/a.png", title="A", kind=MediaKind.IMAGE)
        )
        second = repos.media.add(
            MediaItem(path="C:/a.png", title="A bis", kind=MediaKind.IMAGE)
        )
        assert first == second
        assert repos.media.count() == 1

    def test_recherche_tags_et_favoris(self, repos):
        a = repos.media.add(
            MediaItem(path="C:/paysage.png", title="Paysage", kind=MediaKind.IMAGE)
        )
        b = repos.media.add(
            MediaItem(path="C:/ville.mp4", title="Ville", kind=MediaKind.VIDEO)
        )
        repos.media.set_tags(a, ["nature", "calme"])
        repos.media.set_favorite(b, True)

        assert [m.title for m in repos.media.list(search="pays")] == ["Paysage"]
        assert [m.title for m in repos.media.list(tag="nature")] == ["Paysage"]
        assert [m.title for m in repos.media.list(favorites_only=True)] == ["Ville"]
        assert [m.title for m in repos.media.list(kinds=[MediaKind.VIDEO])] == ["Ville"]
        assert sorted(repos.media.all_tags()) == ["calme", "nature"]

    def test_collections(self, repos):
        media_id = repos.media.add(
            MediaItem(path="C:/a.png", title="A", kind=MediaKind.IMAGE)
        )
        collection_id = repos.collections.create("Favoris du mois")
        repos.collections.add_media(collection_id, media_id)

        collections = repos.collections.list()
        assert collections[0].name == "Favoris du mois"
        assert collections[0].count == 1
        assert len(repos.media.list(collection_id=collection_id)) == 1

        repos.collections.remove_media(collection_id, media_id)
        assert repos.collections.list()[0].count == 0
