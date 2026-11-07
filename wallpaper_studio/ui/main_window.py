"""Fenetre principale : navigation laterale et assemblage des pages."""

from __future__ import annotations

import logging
from typing import Dict, Optional

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt, Signal
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QButtonGroup,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .. import APP_NAME, APP_VERSION
from ..data.models import MediaItem
from ..media.types import MediaKind
from .changelog_view import ChangelogView
from .editor_view import EditorView
from .history_view import HistoryView
from .home_view import HomeView
from .library_view import LibraryView
from .monitor_view import MonitorView
from .performance_view import PerformanceView
from .scheduler_view import SchedulerView
from .settings_view import SettingsView
from ..i18n import tr
from .theme import app_icon, icon, stylesheet
from .translate_tree import translate_tree
from .widgets.common import Toast

log = logging.getLogger(__name__)

PAGES = [
    ("home", "Accueil", "accueil"),
    ("library", "Bibliotheque", "bibliotheque"),
    ("monitors", "Ecrans", "ecrans"),
    ("scheduler", "Horaires", "horaires"),
    ("editor", "Editeur", "editeur"),
    ("performance", "Performances", "performances"),
    ("history", "Historique", "historique"),
    ("changelog", "Nouveautes", "nouveautes"),
    ("settings", "Parametres", "parametres"),
]


class MainWindow(QWidget):
    """Fenetre principale de l'application."""

    closing_to_tray = Signal()
    #: Demande la fermeture complete (installation d'une mise a jour).
    quit_requested = Signal()

    def __init__(self, controller, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._controller = controller
        self._pages: Dict[str, QWidget] = {}
        self._buttons: Dict[str, QPushButton] = {}
        self._force_quit = False
        self._preview_item = None
        self._update_checker = None

        self.setWindowTitle(f"{APP_NAME} {APP_VERSION}")
        self.setWindowIcon(app_icon(64))
        self.resize(1240, 800)
        self.setMinimumSize(1020, 660)
        self.setStyleSheet(stylesheet(controller.settings.get("theme", "sombre")))

        self._build()
        self._connect()
        translate_tree(self)

    # --- Construction ------------------------------------------------------
    def _build(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # --- Barre laterale ---
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(214)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(10, 0, 10, 14)
        side.setSpacing(3)

        title = QLabel(APP_NAME)
        title.setObjectName("appTitle")
        title.setWordWrap(True)
        side.addWidget(title)

        subtitle = QLabel("Fonds d'ecran animes")
        subtitle.setObjectName("appSubtitle")
        side.addWidget(subtitle)

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        for key, label, icon_name in PAGES:
            button = QPushButton(f"  {label}")
            button.setObjectName("navButton")
            button.setIcon(icon(icon_name))
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(lambda _=False, k=key: self.show_page(k))
            self._group.addButton(button)
            side.addWidget(button)
            self._buttons[key] = button

        side.addStretch(1)

        self._sidebar_status = QLabel()
        self._sidebar_status.setObjectName("hint")
        self._sidebar_status.setWordWrap(True)
        side.addWidget(self._sidebar_status)
        root.addWidget(sidebar)

        # --- Pages ---
        self._stack = QStackedWidget()
        root.addWidget(self._stack, 1)

        # Les pages ne sont PAS construites ici : chacune est creee a sa
        # premiere ouverture (voir :meth:`_page`). Construire les huit pages au
        # demarrage coutait 78 Mo, alors que l'utilisateur n'en consulte
        # souvent que deux ou trois.
        self.show_page("home")

    # --- Creation paresseuse des pages -------------------------------------
    def _build_page(self, key: str) -> QWidget:
        """Construit une page et raccorde ses signaux."""
        controller = self._controller

        if key == "home":
            page = HomeView(controller.engine, controller.repos,
                            controller.scheduler, controller.settings)
            page.navigate.connect(self.show_page)
        elif key == "library":
            page = LibraryView(controller.repos, controller.settings)
            page.apply_requested.connect(self._apply_media_item)
            page.preview_requested.connect(self._on_preview)
            page.edit_requested.connect(self._open_in_editor)
            page.schedule_requested.connect(self._schedule_for_item)
        elif key == "monitors":
            page = MonitorView(controller.engine, controller.repos,
                               controller.settings)
            page.apply_to_monitor.connect(self._apply_selection_to_monitor)
            page.clear_monitor.connect(self._clear_monitor)
            page.restore_previous.connect(controller.restore_previous)
            page.pause_monitor.connect(self._pause_monitor)
            page.settings_changed.connect(self._on_monitor_settings)
            page.same_on_all_requested.connect(self._apply_same_on_all)
            page.span_requested.connect(self._apply_span)
        elif key == "scheduler":
            page = SchedulerView(controller.repos, controller.engine,
                                 controller.scheduler, controller.settings)
        elif key == "editor":
            page = EditorView(controller.repos, controller.settings)
            page.apply_requested.connect(self._apply_from_editor)
            if self._preview_item is not None:
                page.load_item(self._preview_item)
        elif key == "performance":
            page = PerformanceView(controller.engine, controller.perf,
                                   controller.settings)
        elif key == "history":
            page = HistoryView(controller.repos, controller.engine)
            page.reapply_requested.connect(self._reapply_from_history)
        elif key == "changelog":
            page = ChangelogView(controller.settings)
            page.check_requested.connect(lambda: self.check_for_updates(manuel=True))
        elif key == "settings":
            page = SettingsView(controller.settings, controller.repos,
                                controller.engine)
            page.theme_changed.connect(self._apply_theme)
            page.settings_applied.connect(self._on_settings_applied)
        else:
            raise KeyError(key)

        if hasattr(page, "notify"):
            page.notify.connect(self.toast)
        # La page vient d'etre construite en francais : on la traduit avant
        # qu'elle soit affichee (sans effet si la langue active est le francais).
        translate_tree(page)
        self._pages[key] = page
        self._stack.addWidget(page)
        log.debug("Page « %s » construite a la demande", key)
        return page

    def _page(self, key: str) -> QWidget:
        """Page demandee, construite si c'est sa premiere ouverture."""
        page = self._pages.get(key)
        return page if page is not None else self._build_page(key)

    def _existing(self, key: str) -> Optional[QWidget]:
        """Page deja construite, ou ``None`` : n'en cree jamais une."""
        return self._pages.get(key)

    # --- Connexions --------------------------------------------------------
    def _connect(self) -> None:
        controller = self._controller
        controller.notify.connect(self.toast)

        # Moteur
        controller.engine.playback_failed.connect(self._on_playback_failed)
        controller.engine.monitors_changed.connect(self._on_monitors_changed)
        controller.engine.host_recovered.connect(
            lambda: self.toast("Couche de bureau retablie apres un redemarrage "
                               "de l'Explorateur.", "info")
        )
        controller.state_changed.connect(self._refresh_light)
        controller.perf.auto_pause_changed.connect(self._on_auto_pause)
        controller.scheduler.on_evaluated = self._refresh_sidebar

    # --- Navigation --------------------------------------------------------
    def show_page(self, key: str) -> None:
        if key not in {k for k, _, _ in PAGES}:
            return
        page = self._page(key)

        button = self._buttons.get(key)
        if button and not button.isChecked():
            button.setChecked(True)

        if self._stack.currentWidget() is not page:
            self._stack.setCurrentWidget(page)
            # Fondu discret a l'entree de la page.
            effect = QGraphicsOpacityEffect(page)
            page.setGraphicsEffect(effect)
            animation = QPropertyAnimation(effect, b"opacity", page)
            animation.setDuration(170)
            animation.setStartValue(0.35)
            animation.setEndValue(1.0)
            animation.setEasingCurve(QEasingCurve.OutCubic)
            animation.finished.connect(lambda: page.setGraphicsEffect(None))
            animation.start(QPropertyAnimation.DeleteWhenStopped)

        if hasattr(page, "refresh"):
            page.refresh()

    def toast(self, message: str, kind: str = "info") -> None:
        Toast(self, message, kind)

    # --- Actions bibliotheque ---------------------------------------------
    def _current_monitor_key(self) -> Optional[str]:
        """Ecran cible : celui selectionne dans la page Ecrans, sinon le principal."""
        monitors = self._existing("monitors")
        key = monitors.selected_key() if monitors is not None else None
        if key:
            return key
        primary = self._controller.monitors.primary()
        return primary.key if primary else None

    def _apply_media_item(self, item: MediaItem) -> None:
        if item.missing:
            self.toast("Ce fichier est introuvable sur le disque.", "erreur")
            return
        key = self._current_monitor_key()
        if key is None:
            self.toast("Aucun ecran detecte.", "erreur")
            return
        if self._controller.apply_media(key, item.id, reason="manuel"):
            self.toast(f"« {item.title} » applique.", "succes")
            self._refresh_light()

    def _on_preview(self, item: MediaItem) -> None:
        # Un simple clic dans la bibliotheque ne doit pas construire l'editeur :
        # on memorise la selection, l'editeur la chargera a son ouverture.
        self._preview_item = item
        editor = self._existing("editor")
        if editor is not None:
            editor.load_item(item)

    def _open_in_editor(self, item: MediaItem) -> None:
        self._page("editor").load_item(item)
        self.show_page("editor")

    def _schedule_for_item(self, item: MediaItem) -> None:
        self.show_page("scheduler")
        self._page("scheduler").create_rule(media_id=item.id)

    # --- Actions ecrans ----------------------------------------------------
    def _apply_selection_to_monitor(self, monitor_key: str) -> None:
        library = self._existing("library")
        item = library.selected_item() if library is not None else None
        if item is None:
            self.toast(
                "Choisissez d'abord un fond dans la bibliotheque.", "info"
            )
            self.show_page("library")
            return
        if self._controller.apply_media(monitor_key, item.id, reason="manuel"):
            self.toast(f"« {item.title} » applique sur cet ecran.", "succes")
            self._refresh_light()

    def _clear_monitor(self, monitor_key: str) -> None:
        self._controller.engine.clear(monitor_key)
        self._controller.repos.monitors.set_media(monitor_key, None)
        self._refresh_light()
        self.toast("Fond retire de cet ecran.", "info")

    def _pause_monitor(self, monitor_key: str, paused: bool) -> None:
        if paused:
            self._controller.engine.pause_screen(monitor_key)
        else:
            self._controller.engine.resume_screen(monitor_key)
        self._refresh_light()

    def _on_monitor_settings(self, monitor_key: str) -> None:
        config = self._controller.repos.monitors.get(monitor_key)
        if config:
            self._controller.save_monitor_config(config)

    def _apply_same_on_all(self) -> None:
        library = self._existing("library")
        item = library.selected_item() if library is not None else None
        if item is None:
            self.toast("Choisissez d'abord un fond dans la bibliotheque.", "info")
            self.show_page("library")
            return
        count = self._controller.apply_to_all(item.id)
        self.toast(f"Fond applique sur {count} ecran(s).", "succes")
        self._refresh_light()

    def _apply_span(self) -> None:
        library = self._existing("library")
        item = library.selected_item() if library is not None else None
        if item is None:
            self.toast("Choisissez d'abord une image dans la bibliotheque.", "info")
            self.show_page("library")
            return
        count = self._controller.apply_span(item.id)
        if count:
            self.toast(f"Image repartie sur {count} ecran(s).", "succes")
            self._refresh_light()

    # --- Editeur -----------------------------------------------------------
    def _apply_from_editor(self, item, adjustments, fill_mode, effects) -> None:
        key = self._current_monitor_key()
        if key is None:
            self.toast("Aucun ecran detecte.", "erreur")
            return
        ok = self._controller.apply_media(
            key, item.id, reason="manuel",
            adjustments=adjustments, fill_mode=fill_mode, effects=effects,
        )
        if ok:
            # Memorise les reglages pour cet ecran.
            config = self._controller.repos.monitors.get_or_create(key)
            config.adjustments = adjustments
            config.fill_mode = fill_mode
            config.effects = list(effects)
            self._controller.repos.monitors.save(config)
            self.toast("Modifications appliquees au fond d'ecran.", "succes")
            self._refresh_light()

    def _reapply_from_history(self, media_id: int) -> None:
        key = self._current_monitor_key()
        if key and self._controller.apply_media(key, media_id, reason="manuel"):
            self.toast("Fond reapplique.", "succes")
            self._refresh_light()

    # --- Reactions du moteur ----------------------------------------------
    def _on_playback_failed(self, monitor_key: str, message: str) -> None:
        monitor = self._controller.monitors.by_key(monitor_key)
        label = monitor.label if monitor else monitor_key
        self.toast(f"{label} : {message}", "erreur")
        monitors = self._existing("monitors")
        if monitors is not None:
            monitors.refresh()

    def _on_monitors_changed(self) -> None:
        for key in ("monitors", "home"):
            page = self._existing(key)
            if page is not None:
                page.refresh()
        self.toast("Configuration des ecrans modifiee.", "info")

    def _on_auto_pause(self, paused: bool, reason: str) -> None:
        if paused:
            self.toast(f"Fonds mis en pause : {reason}.", "info")

    def _on_settings_applied(self) -> None:
        controller = self._controller
        controller.engine.set_fps_cap(controller.settings.fps_cap)
        controller.scheduler.set_enabled(
            bool(controller.settings.get("planification_active", True))
        )
        performance = self._existing("performance")
        if performance is not None:
            performance.refresh_from_settings()

    def _apply_theme(self, theme: str) -> None:
        self.setStyleSheet(stylesheet(theme))
        self.toast(f"Theme « {theme} » applique.", "succes")

    # --- Rafraichissement --------------------------------------------------
    def _refresh_light(self) -> None:
        """Rafraichit les pages sensibles a l'etat, sans tout recharger."""
        current = self._stack.currentWidget()
        for key in ("home", "monitors"):
            page = self._existing(key)
            if page is not None and page is current:
                page.refresh()
        self._refresh_sidebar()

    def _refresh_sidebar(self) -> None:
        controller = self._controller
        engine = controller.engine
        self._sidebar_status.setText(
            f"{engine.active_count} fond(s) actif(s)\n"
            f"{controller.scheduler.describe_next()}"
        )

    # --- Mises a jour ------------------------------------------------------
    def check_for_updates(self, manuel: bool = False) -> None:
        """Interroge GitHub en arriere-plan.

        ``manuel`` distingue une recherche demandee par l'utilisateur, qui
        merite une reponse meme quand tout est a jour, d'une verification
        automatique au demarrage, qui doit rester silencieuse.
        """
        from .update_dialog import UpdateChecker

        if self._update_checker is not None and self._update_checker.isRunning():
            return
        self._update_checker = UpdateChecker(self)
        self._update_checker.fini.connect(
            lambda release, erreur: self._on_update_checked(release, erreur, manuel)
        )
        self._update_checker.start()

    def _on_update_checked(self, release, erreur, manuel: bool) -> None:
        page = self._existing("changelog")

        if erreur:
            log.info("Recherche de mise a jour : %s", erreur)
            if page is not None:
                page.set_check_result(erreur)
            if manuel:
                self.toast(erreur, "alerte")
            return

        if release is None:
            message = tr("Vous utilisez la derniere version.")
            if page is not None:
                page.set_check_result(message)
            if manuel:
                self.toast(message, "succes")
            return

        if page is not None:
            page.set_check_result(
                f"{tr('Une mise a jour est disponible')} : {release.version}"
            )
        self._show_update_dialog(release)

    def _show_update_dialog(self, release) -> None:
        from .update_dialog import UpdateDialog

        dialogue = UpdateDialog(
            release, self, self._controller.settings.get("theme", "sombre")
        )
        dialogue.install_requested.connect(self._install_update)
        dialogue.exec()

    def _install_update(self, fichier) -> None:
        from .update_dialog import apply_update

        if apply_update(fichier):
            self.toast(tr("Mise a jour prete"), "succes")
            # L'installateur a besoin que l'application soit fermee.
            self.quit_requested.emit()
        else:
            self.toast("Installation impossible : fichier introuvable.", "erreur")

    # --- Gel de l'interface quand elle n'est pas visible -------------------
    def _set_ui_active(self, active: bool) -> None:
        """Suspend ou reprend les rafraichissements periodiques des pages.

        Fenetre fermee dans la zone de notification, l'interface n'a plus rien
        a montrer : laisser tourner ses minuteurs reviendrait a interroger la
        base et le moteur plusieurs fois par seconde pour rien.
        """
        for page in self._pages.values():
            setter = getattr(page, "set_updates_active", None)
            if setter is not None:
                setter(active)
        self._controller.perf.set_ui_visible(active)
        log.debug("Rafraichissements de l'interface : %s",
                  "actifs" if active else "suspendus")

    def showEvent(self, event) -> None:  # noqa: N802 - API Qt
        super().showEvent(event)
        self._set_ui_active(True)
        current = self._stack.currentWidget()
        if current is not None and hasattr(current, "refresh"):
            current.refresh()

    def hideEvent(self, event) -> None:  # noqa: N802 - API Qt
        super().hideEvent(event)
        self._set_ui_active(False)

    def release(self) -> None:
        """Detache tout ce qui survivrait a la destruction de la fenetre.

        Les connexions de signaux Qt se defont seules quand le recepteur est
        detruit, mais ``scheduler.on_evaluated`` est une simple reference
        Python : laissee en place, elle maintiendrait la fenetre en memoire et
        appellerait un objet C++ detruit.
        """
        if self._controller.scheduler.on_evaluated == self._refresh_sidebar:
            self._controller.scheduler.on_evaluated = None
        self._set_ui_active(False)

    # --- Fermeture ---------------------------------------------------------
    def force_quit(self) -> None:
        self._force_quit = True
        self.close()

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 - API Qt
        """Ferme vers la zone de notification plutot que d'arreter le moteur."""
        if self._force_quit:
            event.accept()
            return

        if self._controller.settings.get("fermer_vers_zone_notification", True):
            event.ignore()
            self.hide()
            self.closing_to_tray.emit()
            return

        answer = QMessageBox.question(
            self, "Quitter",
            "Quitter completement Wallpaper Studio ?\n\n"
            "Les fonds d'ecran animes et le planificateur seront arretes.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if answer == QMessageBox.Yes:
            event.accept()
        else:
            event.ignore()
