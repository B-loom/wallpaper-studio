"""Tests de la traduction, du choix de langue et de la mise a jour."""

from __future__ import annotations

import json

import pytest

from wallpaper_studio import i18n
from wallpaper_studio.system import updater

pytestmark = pytest.mark.usefixtures("qapp")


@pytest.fixture(autouse=True)
def langue_francaise():
    """Chaque test repart du francais, langue source."""
    yield
    i18n.set_language("fr")


# --- Catalogue de traduction -----------------------------------------------
class TestCatalogue:
    def test_le_francais_est_la_langue_source(self):
        i18n.set_language("fr")
        assert i18n.current_language() == "fr"
        # Sans catalogue, une chaine se traduit par elle-meme.
        assert i18n.tr("Bibliotheque") == "Bibliotheque"

    def test_le_catalogue_anglais_se_charge(self):
        assert i18n.set_language("en") is True
        assert i18n.current_language() == "en"
        assert i18n.catalog_size() > 150

    def test_traductions_attendues(self):
        i18n.set_language("en")
        for source, attendu in (
            ("Bibliotheque", "Library"),
            ("Horaires", "Schedule"),
            ("Parametres", "Settings"),
            ("Nouveautes", "What's new"),
            ("Appliquer maintenant", "Apply now"),
        ):
            assert i18n.tr(source) == attendu

    def test_chaine_absente_reste_en_francais(self):
        i18n.set_language("en")
        assert i18n.tr("Chaine jamais traduite") == "Chaine jamais traduite"

    def test_has_translation(self):
        i18n.set_language("en")
        assert i18n.has_translation("Bibliotheque")
        assert not i18n.has_translation("Chaine jamais traduite")

    def test_langue_inconnue_refusee_sans_casse(self):
        assert i18n.set_language("zz") is False
        # La langue precedente reste active.
        assert i18n.current_language() in ("fr", "en")

    def test_langues_disponibles(self):
        codes = {c for c, _ in i18n.available_languages()}
        assert "fr" in codes and "en" in codes

    def test_le_catalogue_est_un_json_valide(self):
        chemin = i18n.lang_dir() / "en.json"
        donnees = json.loads(chemin.read_text(encoding="utf-8"))
        assert donnees["_meta"]["code"] == "en"
        # Aucune traduction vide, qui afficherait un libelle disparu.
        vides = [k for k, v in donnees.items() if k != "_meta" and not str(v).strip()]
        assert vides == [], f"traductions vides : {vides}"


# --- Traduction de l'arbre de widgets --------------------------------------
class TestTraductionInterface:
    def test_un_widget_est_traduit(self):
        from PySide6.QtWidgets import QLabel, QPushButton, QWidget, QVBoxLayout

        from wallpaper_studio.ui.translate_tree import translate_tree

        i18n.set_language("en")
        racine = QWidget()
        corps = QVBoxLayout(racine)
        etiquette = QLabel("Bibliotheque")
        bouton = QPushButton("Appliquer maintenant")
        corps.addWidget(etiquette)
        corps.addWidget(bouton)

        translate_tree(racine)
        assert etiquette.text() == "Library"
        assert bouton.text() == "Apply now"

    def test_aucun_effet_en_francais(self):
        from PySide6.QtWidgets import QLabel

        from wallpaper_studio.ui.translate_tree import translate_tree

        i18n.set_language("fr")
        etiquette = QLabel("Bibliotheque")
        assert translate_tree(etiquette) == 0
        assert etiquette.text() == "Bibliotheque"

    def test_les_espaces_de_mise_en_forme_sont_conserves(self):
        from PySide6.QtWidgets import QPushButton

        from wallpaper_studio.ui.translate_tree import translate_tree

        i18n.set_language("en")
        bouton = QPushButton("  Importer des fichiers")
        translate_tree(bouton)
        assert bouton.text() == "  Import files"

    def test_la_navigation_est_entierement_traduite(self, isolated_data):
        from wallpaper_studio.app import AppController
        from wallpaper_studio.ui.main_window import MainWindow, PAGES
        from PySide6.QtWidgets import QPushButton

        i18n.set_language("en")
        ctrl = AppController()
        fenetre = MainWindow(ctrl)
        try:
            libelles = [
                b.text().strip()
                for b in fenetre.findChildren(QPushButton)
                if b.objectName() == "navButton"
            ]
            assert len(libelles) == len(PAGES)
            # Plus aucun libelle francais d'origine.
            francais = {label for _, label, _ in PAGES}
            restants = [n for n in libelles if n in francais and n != "Performances"]
            assert restants == [], f"non traduits : {restants}"
        finally:
            fenetre.release()
            fenetre.deleteLater()
            ctrl.shutdown()


# --- Notes de version -------------------------------------------------------
class TestNotesDeVersion:
    def test_les_deux_langues_existent_et_different(self):
        from wallpaper_studio.ui.changelog_view import changelog_text

        fr = changelog_text("fr")
        en = changelog_text("en")
        assert len(fr) > 300 and len(en) > 300
        assert fr != en
        assert "Nouveautes" in fr or "Nouveautés" in fr
        assert "What's new" in en

    def test_repli_sur_le_francais(self):
        from wallpaper_studio.ui.changelog_view import changelog_text

        # Une langue sans fichier de notes retombe sur le francais.
        assert changelog_text("zz") == changelog_text("fr")


# --- Mise a jour ------------------------------------------------------------
class TestComparaisonVersions:
    @pytest.mark.parametrize(
        "candidate,reference,attendu",
        [
            ("1.0.1", "1.0.0", True),
            ("1.1.0", "1.0.9", True),
            ("2.0.0", "1.9.9", True),
            ("v1.2.0", "1.1.0", True),
            ("1.0.0", "1.0.0", False),
            ("0.9.9", "1.0.0", False),
            ("1.0", "1.0.0", False),
            ("1.10.0", "1.9.0", True),
        ],
    )
    def test_comparaison(self, candidate, reference, attendu):
        assert updater.is_newer(candidate, reference) is attendu

    def test_le_tri_est_numerique_et_non_alphabetique(self):
        """« 1.10 » doit etre vu comme plus recent que « 1.9 »."""
        assert updater.is_newer("1.10.0", "1.9.0")
        assert not updater.is_newer("1.9.0", "1.10.0")


class TestSecuriteTelechargement:
    @pytest.mark.parametrize(
        "url,autorisee",
        [
            ("https://github.com/o/r/releases/download/v1/a.exe", True),
            ("https://api.github.com/repos/o/r/releases/latest", True),
            ("https://objects.githubusercontent.com/x", True),
            ("http://github.com/o/r/a.exe", False),          # pas de HTTPS
            ("https://evil.com/a.exe", False),                # autre domaine
            ("https://github.com.evil.com/a.exe", False),     # domaine trompeur
            ("ftp://github.com/a.exe", False),
            ("", False),
        ],
    )
    def test_adresses(self, url, autorisee):
        assert updater._url_sure(url) is autorisee

    def test_telechargement_refuse_une_adresse_non_github(self, tmp_path):
        faux = updater.Release(
            version="9.9.9", nom="x", notes="", url_page="",
            url_fichier="https://evil.com/malware.exe",
            nom_fichier="malware.exe",
        )
        chemin, erreur = updater.download_release(faux)
        assert chemin is None
        assert erreur and "refus" in erreur.lower()

    def test_version_sans_fichier(self):
        sans = updater.Release(
            version="9.9.9", nom="x", notes="", url_page="",
            url_fichier=None, nom_fichier=None,
        )
        assert not sans.telechargeable
        chemin, erreur = updater.download_release(sans)
        assert chemin is None and erreur


class TestChoixDeLangue:
    def test_la_question_n_est_posee_qu_une_fois(self, tmp_path):
        from wallpaper_studio.data.settings import Settings
        from wallpaper_studio.ui.welcome_dialog import ask_language_if_needed

        reglages = Settings(path=tmp_path / "r.json")
        # Langue deja choisie : aucune question, donc aucun dialogue bloquant.
        reglages.set("langue_choisie", True)
        assert ask_language_if_needed(reglages) is None

    def test_le_temoin_est_faux_par_defaut(self, tmp_path):
        from wallpaper_studio.data.settings import Settings

        reglages = Settings(path=tmp_path / "r.json")
        assert reglages.get("langue_choisie") is False
        assert reglages.get("langue") == "fr"
