"""Page Parametres : general, moteur, planificateur, sauvegarde."""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .. import APP_VERSION
from ..app_paths import config_dir, data_dir, database_path, log_dir
from ..data.settings import (
    IMPORT_COPIER,
    IMPORT_DEMANDER,
    IMPORT_REFERENCER,
    THEME_CLAIR,
    THEME_SOMBRE,
)
from ..i18n import available_languages
from ..system import autostart
from .widgets.common import hint_label

log = logging.getLogger(__name__)


class SettingsView(QWidget):
    """Page Parametres."""

    theme_changed = Signal(str)
    language_changed = Signal(str)
    settings_applied = Signal()
    notify = Signal(str, str)

    def __init__(self, settings, repos, engine, parent=None):
        super().__init__(parent)
        self._settings = settings
        self._repos = repos
        self._engine = engine
        self._loading = False
        self._build()
        self.reload()

    # --- Construction ------------------------------------------------------
    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(12)

        title = QLabel("Parametres")
        title.setObjectName("pageTitle")
        outer.addWidget(title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        root = QVBoxLayout(content)
        root.setSpacing(14)
        root.setContentsMargins(0, 0, 14, 0)

        # --- General ---
        general = QGroupBox("General")
        form = QFormLayout(general)

        self._language = QComboBox()
        for code, name in available_languages():
            self._language.addItem(name, code)
        self._language.currentIndexChanged.connect(self._on_language)
        form.addRow("Langue :", self._language)

        self._theme = QComboBox()
        self._theme.addItem("Sombre", THEME_SOMBRE)
        self._theme.addItem("Clair", THEME_CLAIR)
        self._theme.currentIndexChanged.connect(self._on_theme)
        form.addRow("Theme :", self._theme)

        self._autostart = QCheckBox("Lancer Wallpaper Studio au demarrage de Windows")
        self._autostart.toggled.connect(self._on_autostart)
        form.addRow("", self._autostart)

        self._start_minimized = QCheckBox("Demarrer dans la zone de notification")
        self._start_minimized.toggled.connect(
            lambda v: self._set("demarrer_minimise", v)
        )
        form.addRow("", self._start_minimized)

        self._close_to_tray = QCheckBox(
            "Fermer la fenetre reduit dans la zone de notification "
            "(le planificateur continue)"
        )
        self._close_to_tray.toggled.connect(
            lambda v: self._set("fermer_vers_zone_notification", v)
        )
        form.addRow("", self._close_to_tray)

        self._free_ui = QCheckBox(
            "Liberer la memoire de l'interface quand la fenetre est fermee"
        )
        self._free_ui.setToolTip(
            "Detruit l'interface 45 secondes apres sa fermeture et rend "
            "environ 70 Mo. La fenetre se reconstruit a la reouverture."
        )
        self._free_ui.toggled.connect(
            lambda v: self._set("liberer_interface_en_arriere_plan", v)
        )
        form.addRow("", self._free_ui)

        self._maj = QCheckBox("Rechercher les mises a jour au demarrage")
        self._maj.setToolTip(
            "Interroge la page des versions du projet sur GitHub. "
            "Aucune donnee personnelle n'est transmise."
        )
        self._maj.toggled.connect(lambda v: self._set("verifier_maj_au_demarrage", v))
        form.addRow("", self._maj)

        self._notifications = QCheckBox("Afficher les notifications")
        self._notifications.toggled.connect(lambda v: self._set("notifications", v))
        form.addRow("", self._notifications)
        root.addWidget(general)

        # --- Bibliotheque ---
        library = QGroupBox("Bibliotheque")
        lib_form = QFormLayout(library)

        folder_row = QHBoxLayout()
        self._library_dir = QLineEdit()
        self._library_dir.setReadOnly(True)
        folder_row.addWidget(self._library_dir, 1)
        browse = QPushButton("Parcourir...")
        browse.clicked.connect(self._choose_library)
        folder_row.addWidget(browse)
        lib_form.addRow("Dossier de la bibliotheque :", folder_row)

        self._import_mode = QComboBox()
        self._import_mode.addItem("Demander a chaque import", IMPORT_DEMANDER)
        self._import_mode.addItem("Referencer les fichiers d'origine", IMPORT_REFERENCER)
        self._import_mode.addItem("Copier dans la bibliotheque", IMPORT_COPIER)
        self._import_mode.currentIndexChanged.connect(
            lambda: self._set("mode_import", self._import_mode.currentData())
        )
        lib_form.addRow("Mode d'importation :", self._import_mode)

        self._check_files = QCheckBox("Verifier les fichiers manquants au demarrage")
        self._check_files.toggled.connect(
            lambda v: self._set("verifier_fichiers_au_demarrage", v)
        )
        lib_form.addRow("", self._check_files)

        self._confirm_delete = QCheckBox("Confirmer avant de retirer un fond")
        self._confirm_delete.toggled.connect(lambda v: self._set("confirmer_suppression", v))
        lib_form.addRow("", self._confirm_delete)
        root.addWidget(library)

        # --- Moteur ---
        engine_box = QGroupBox("Moteur multimedia")
        engine_form = QFormLayout(engine_box)

        self._hardware = QCheckBox("Decodage video materiel (recommande)")
        self._hardware.toggled.connect(self._on_hardware)
        engine_form.addRow("", self._hardware)

        self._fps = QSpinBox()
        self._fps.setRange(5, 60)
        self._fps.setSuffix(" images/s")
        self._fps.valueChanged.connect(self._on_fps)
        engine_form.addRow("Plafond d'images par seconde :", self._fps)

        self._global_volume = QSpinBox()
        self._global_volume.setRange(0, 100)
        self._global_volume.setSuffix(" %")
        self._global_volume.valueChanged.connect(
            lambda v: self._set("volume_global", v)
        )
        self._global_volume.setToolTip(
            "Volume applique aux ecrans dont le volume n'a pas ete regle "
            "individuellement."
        )
        engine_form.addRow("Volume par defaut :", self._global_volume)

        self._global_muted = QCheckBox("Couper le son par defaut")
        self._global_muted.toggled.connect(lambda v: self._set("muet_global", v))
        engine_form.addRow("", self._global_muted)

        self._verbose_log = QCheckBox(
            "Journalisation detaillee (utile pour diagnostiquer un probleme)"
        )
        self._verbose_log.toggled.connect(self._on_verbose_log)
        engine_form.addRow("", self._verbose_log)

        self._vlc_status = QLabel()
        self._vlc_status.setObjectName("hint")
        self._vlc_status.setWordWrap(True)
        engine_form.addRow("Lecteur video :", self._vlc_status)
        root.addWidget(engine_box)

        # --- Planificateur ---
        scheduler = QGroupBox("Planificateur")
        sched_form = QFormLayout(scheduler)
        self._scheduler_on = QCheckBox("Appliquer automatiquement les regles horaires")
        self._scheduler_on.toggled.connect(lambda v: self._set("planification_active", v))
        sched_form.addRow("", self._scheduler_on)
        sched_form.addRow(
            "",
            hint_label(
                "Le planificateur continue de fonctionner quand la fenetre est "
                "fermee, tant que l'application reste dans la zone de notification."
            ),
        )
        root.addWidget(scheduler)

        # --- Sauvegarde ---
        backup = QGroupBox("Sauvegarde et restauration")
        backup_layout = QVBoxLayout(backup)
        buttons = QHBoxLayout()
        for label, slot in (
            ("Exporter les reglages", self._export_settings),
            ("Importer des reglages", self._import_settings),
            ("Sauvegarder la base de donnees", self._backup_db),
        ):
            button = QPushButton(label)
            button.clicked.connect(slot)
            buttons.addWidget(button)
        buttons.addStretch(1)
        backup_layout.addLayout(buttons)

        danger = QHBoxLayout()
        reset = QPushButton("Reinitialiser tous les reglages")
        reset.setObjectName("danger")
        reset.clicked.connect(self._reset)
        danger.addWidget(reset)
        danger.addStretch(1)
        backup_layout.addLayout(danger)
        root.addWidget(backup)

        # --- Emplacements ---
        about = QGroupBox("Emplacements et informations")
        about_form = QFormLayout(about)
        about_form.addRow("Version :", QLabel(APP_VERSION))
        for label, path in (
            ("Donnees :", data_dir()),
            ("Base de donnees :", database_path()),
            ("Configuration :", config_dir()),
            ("Journaux :", log_dir()),
        ):
            field = QLineEdit(str(path))
            field.setReadOnly(True)
            about_form.addRow(label, field)

        open_folder = QPushButton("Ouvrir le dossier de donnees")
        open_folder.clicked.connect(self._open_data_dir)
        about_form.addRow("", open_folder)
        root.addWidget(about)

        root.addStretch(1)
        scroll.setWidget(content)
        outer.addWidget(scroll, 1)

    # --- Chargement --------------------------------------------------------
    def reload(self) -> None:
        self._loading = True
        try:
            s = self._settings
            index = self._language.findData(s.get("langue", "fr"))
            self._language.setCurrentIndex(max(0, index))
            index = self._theme.findData(s.get("theme", THEME_SOMBRE))
            self._theme.setCurrentIndex(max(0, index))

            self._autostart.setChecked(autostart.is_enabled())
            self._start_minimized.setChecked(bool(s.get("demarrer_minimise")))
            self._close_to_tray.setChecked(bool(s.get("fermer_vers_zone_notification")))
            self._notifications.setChecked(bool(s.get("notifications")))
            self._maj.setChecked(bool(s.get("verifier_maj_au_demarrage", True)))
            self._free_ui.setChecked(
                bool(s.get("liberer_interface_en_arriere_plan", True))
            )

            self._library_dir.setText(str(s.get("dossier_bibliotheque")))
            index = self._import_mode.findData(s.get("mode_import"))
            self._import_mode.setCurrentIndex(max(0, index))
            self._check_files.setChecked(bool(s.get("verifier_fichiers_au_demarrage")))
            self._confirm_delete.setChecked(bool(s.get("confirmer_suppression")))

            self._hardware.setChecked(bool(s.get("decodage_materiel")))
            self._fps.setValue(int(s.get("limite_fps", 30)))
            self._global_volume.setValue(int(s.get("volume_global", 0)))
            self._global_muted.setChecked(bool(s.get("muet_global", True)))
            self._verbose_log.setChecked(bool(s.get("journal_detaille", False)))
            self._scheduler_on.setChecked(bool(s.get("planification_active")))

            self._refresh_vlc_status()
        finally:
            self._loading = False

    def _refresh_vlc_status(self) -> None:
        from ..engine.backends import vlc_runtime

        version = vlc_runtime.ensure_loaded()
        if version:
            self._vlc_status.setText(
                f"libVLC {version} - {vlc_runtime.vlc_directory()}"
            )
        else:
            self._vlc_status.setText(
                vlc_runtime.init_error()
                or "libVLC non chargee : la lecture video est indisponible."
            )

    # --- Reactions ---------------------------------------------------------
    def _set(self, key: str, value) -> None:
        if not self._loading:
            self._settings.set(key, value)

    def _on_theme(self) -> None:
        if self._loading:
            return
        theme = self._theme.currentData()
        self._settings.set("theme", theme)
        self.theme_changed.emit(theme)

    def _on_language(self) -> None:
        if self._loading:
            return
        code = self._language.currentData()
        self._settings.set("langue", code)
        self.language_changed.emit(code)
        self.notify.emit(
            "Langue enregistree. Redemarrez l'application pour l'appliquer partout.",
            "info",
        )

    def _on_autostart(self, enabled: bool) -> None:
        if self._loading:
            return
        # Le registre Windows est l'unique source de verite : on n'en garde pas
        # de copie dans les reglages, qui pourrait diverger si l'utilisateur
        # desactive l'entree depuis le Gestionnaire des taches.
        ok = autostart.set_enabled(
            enabled, minimized=bool(self._settings.get("demarrer_minimise", False))
        )
        if not ok:
            self.notify.emit(
                "Modification du demarrage automatique impossible "
                "(acces au registre refuse).",
                "erreur",
            )
            self._autostart.blockSignals(True)
            self._autostart.setChecked(autostart.is_enabled())
            self._autostart.blockSignals(False)
        else:
            self.notify.emit(
                "Demarrage automatique " + ("active." if enabled else "desactive."),
                "succes",
            )

    def _on_verbose_log(self, enabled: bool) -> None:
        """Change le niveau de journalisation immediatement, sans redemarrage."""
        if self._loading:
            return
        self._settings.set("journal_detaille", enabled)
        logging.getLogger().setLevel(logging.DEBUG if enabled else logging.INFO)
        for handler in logging.getLogger().handlers:
            handler.setLevel(logging.DEBUG if enabled else logging.INFO)
        self.notify.emit(
            "Journalisation detaillee " + ("activee." if enabled else "desactivee."),
            "succes",
        )

    def _on_hardware(self, enabled: bool) -> None:
        if self._loading:
            return
        self._settings.set("decodage_materiel", enabled)
        self._engine.set_hardware_decode(enabled)

    def _on_fps(self, value: int) -> None:
        if self._loading:
            return
        self._settings.set("limite_fps", value)
        self._engine.set_fps_cap(value)

    def _choose_library(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "Dossier de la bibliotheque", self._library_dir.text()
        )
        if folder:
            self._library_dir.setText(folder)
            self._settings.set("dossier_bibliotheque", folder)
            self.notify.emit("Dossier de la bibliotheque mis a jour.", "succes")

    # --- Sauvegarde --------------------------------------------------------
    def _export_settings(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Exporter les reglages", "reglages.json", "JSON (*.json)"
        )
        if path:
            self._settings.export_to(Path(path))
            self.notify.emit("Reglages exportes.", "succes")

    def _import_settings(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Importer des reglages", "", "JSON (*.json)"
        )
        if not path:
            return
        if self._settings.import_from(Path(path)):
            self.reload()
            self.settings_applied.emit()
            self.notify.emit("Reglages importes.", "succes")
        else:
            self.notify.emit("Fichier de reglages invalide.", "erreur")

    def _backup_db(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Sauvegarder la base", "sauvegarde.db", "Base SQLite (*.db)"
        )
        if path:
            self._repos.db.backup_to(Path(path))
            self.notify.emit("Base de donnees sauvegardee.", "succes")

    def _reset(self) -> None:
        answer = QMessageBox.question(
            self, "Reinitialiser",
            "Retablir tous les reglages par defaut ?\n\n"
            "Votre bibliotheque et vos regles horaires sont conservees.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if answer == QMessageBox.Yes:
            self._settings.reset()
            self.reload()
            self.settings_applied.emit()
            self.theme_changed.emit(self._settings.get("theme"))
            self.notify.emit("Reglages reinitialises.", "succes")

    def _open_data_dir(self) -> None:
        import subprocess

        subprocess.Popen(["explorer", str(data_dir())])
