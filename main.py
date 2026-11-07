r"""Point d'entree de Wallpaper Studio.

Usage :
    python main.py              lance l'application
    python main.py --minimise   demarre dans la zone de notification
    python main.py --selftest   verifie l'environnement et quitte

Ordre de demarrage important : la conscience du DPI doit etre activee *avant*
la creation de ``QApplication``, sinon Qt fige un mode d'echelle incorrect et
les fenetres de fond d'ecran ne couvrent pas exactement les moniteurs.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Permet de lancer le script depuis n'importe quel dossier.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from wallpaper_studio import APP_ID, APP_NAME, APP_VERSION  # noqa: E402
from wallpaper_studio.app_paths import lock_path  # noqa: E402
from wallpaper_studio.logging_setup import setup_logging  # noqa: E402
from wallpaper_studio.system import win_desktop as wd  # noqa: E402

log = logging.getLogger("wallpaper_studio.main")


def _parse_args(argv):
    parser = argparse.ArgumentParser(
        prog="wallpaper-studio", description=f"{APP_NAME} {APP_VERSION}"
    )
    parser.add_argument(
        "--minimise", "--minimized", action="store_true", dest="minimized",
        help="demarrer dans la zone de notification, sans ouvrir la fenetre",
    )
    parser.add_argument(
        "--selftest", action="store_true",
        help="verifier l'environnement (dependances, bureau, ecrans) puis quitter",
    )
    parser.add_argument(
        "--diagnostic", action="store_true",
        help="verifier que le fond s'affiche reellement sur le bureau "
             "(reduit brievement les fenetres puis les restaure)",
    )
    parser.add_argument(
        "--pas-de-reduction", action="store_true", dest="no_minimize",
        help="avec --diagnostic : ne pas reduire les fenetres automatiquement",
    )
    parser.add_argument(
        "--debug", action="store_true", help="journalisation detaillee"
    )
    return parser.parse_args(argv)


def run_selftest() -> int:
    """Verifie que tout ce dont l'application a besoin est disponible."""
    print(f"{APP_NAME} {APP_VERSION} - verification de l'environnement\n")
    ok = True

    print(f"  Python                 : {sys.version.split()[0]}")

    try:
        import PySide6

        print(f"  PySide6                : {PySide6.__version__}")
    except ImportError as exc:
        print(f"  PySide6                : ABSENT ({exc})")
        ok = False

    dpi = wd.enable_dpi_awareness()
    print(f"  Conscience du DPI      : {dpi}")

    host = wd.find_wallpaper_host()
    if host is None:
        print("  Couche de bureau       : INTROUVABLE")
        ok = False
    else:
        print(f"  Couche de bureau       : {host.layout} (hwnd={host.hwnd})")

    from wallpaper_studio.system.monitors import enumerate_monitors

    monitors = enumerate_monitors()
    print(f"  Ecrans detectes        : {len(monitors)}")
    for monitor in monitors:
        print(f"      - {monitor.describe()}")

    from wallpaper_studio.engine.backends import vlc_runtime

    version = vlc_runtime.libvlc_version() or (
        vlc_runtime.init_vlc() and vlc_runtime.libvlc_version()
    )
    if version:
        print(f"  libVLC                 : {version} ({vlc_runtime.vlc_directory()})")
    else:
        print(f"  libVLC                 : ABSENTE - {vlc_runtime.init_error()}")
        print("      (les images fonctionnent, pas les videos)")

    from wallpaper_studio.media.probe import ffmpeg_path, ffprobe_path

    print(f"  ffmpeg                 : {ffmpeg_path() or 'absent (vignettes video limitees)'}")
    print(f"  ffprobe                : {ffprobe_path() or 'absent (metadonnees limitees)'}")

    try:
        from wallpaper_studio.engine.backends.web_backend import WEBENGINE_AVAILABLE

        print(f"  QtWebEngine            : {'present' if WEBENGINE_AVAILABLE else 'absent'}")
    except ImportError:
        print("  QtWebEngine            : absent")

    rivals = wd.detect_rival_wallpaper_apps()
    if rivals:
        print(f"  ATTENTION              : {', '.join(rivals)} occupe deja la couche "
              "de fond d'ecran")

    from wallpaper_studio.app_paths import data_dir, database_path

    print(f"  Dossier de donnees     : {data_dir()}")
    print(f"  Base de donnees        : {database_path()}")

    print("\nResultat :", "environnement correct" if ok else "PROBLEMES DETECTES")
    return 0 if ok else 1


def run_diagnostic(auto_minimize: bool = True) -> int:
    """Verifie de bout en bout que le fond s'affiche sur le bureau."""
    wd.enable_dpi_awareness()

    from PySide6.QtWidgets import QApplication

    from wallpaper_studio.app_paths import cache_dir
    from wallpaper_studio.system.diagnostic import format_report, run_diagnostic as _run

    app = QApplication(sys.argv)  # noqa: F841 - necessaire au rendu Qt

    print("\nDiagnostic en cours...")
    if auto_minimize:
        print("Les fenetres vont etre reduites quelques secondes, puis restaurees.")
        print("Regardez votre bureau : une mire magenta et cyan doit apparaitre.\n")

    result = _run(cache_dir() / "diagnostic", auto_minimize=auto_minimize)
    print(format_report(result))
    return 0 if result.success else 1


def main(argv=None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    setup_logging(logging.DEBUG if args.debug else logging.INFO)

    if args.selftest:
        return run_selftest()

    if args.diagnostic:
        return run_diagnostic(auto_minimize=not args.no_minimize)

    # Doit preceder la creation de QApplication.
    dpi_mode = wd.enable_dpi_awareness()
    log.info("%s %s - conscience du DPI : %s", APP_NAME, APP_VERSION, dpi_mode)

    from PySide6.QtCore import QLockFile, Qt, QTimer
    from PySide6.QtWidgets import QApplication, QMessageBox

    # Instance unique : deux moteurs se disputeraient la couche WorkerW.
    lock = QLockFile(str(lock_path()))
    lock.setStaleLockTime(30_000)
    if not lock.tryLock(100):
        app = QApplication(sys.argv)
        QMessageBox.information(
            None, APP_NAME,
            f"{APP_NAME} est deja en cours d'execution.\n\n"
            "Ouvrez-le depuis l'icone de la zone de notification Windows.",
        )
        log.warning("Instance deja active, demarrage annule")
        return 0

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName(APP_ID)
    # Indispensable : sans cela, fermer la fenetre arreterait l'application et
    # donc le planificateur.
    app.setQuitOnLastWindowClosed(False)

    from wallpaper_studio.app import AppController
    from wallpaper_studio.i18n import set_language
    from wallpaper_studio.system import autostart
    from wallpaper_studio.ui.main_window import MainWindow
    from wallpaper_studio.ui.theme import app_icon
    from wallpaper_studio.ui.tray import TrayIcon

    app.setWindowIcon(app_icon(64))

    controller = AppController()

    # Premier lancement : on demande la langue avant d'afficher l'interface.
    from wallpaper_studio.ui.welcome_dialog import ask_language_if_needed

    ask_language_if_needed(controller.settings)

    if controller.settings.get("journal_detaille", False):
        logging.getLogger().setLevel(logging.DEBUG)
        for handler in logging.getLogger().handlers:
            handler.setLevel(logging.DEBUG)
        log.info("Journalisation detaillee activee par les reglages")
    set_language(controller.settings.get("langue", "fr"))
    autostart.refresh_if_needed(
        bool(controller.settings.get("demarrer_minimise", False))
    )

    tray = TrayIcon(controller)

    # La fenetre principale n'est construite qu'a sa premiere ouverture.
    # Demarre dans la zone de notification, l'application economise ainsi
    # toute l'interface : environ 85 Mo qui ne servaient a rien.
    holder: dict = {"window": None}

    # Delai avant de liberer l'interface : rouvrir la fenetre dans la minute
    # qui suit reste instantane, au-dela la memoire est rendue.
    release_timer = QTimer()
    release_timer.setSingleShot(True)
    release_timer.setInterval(45_000)

    def get_window(create: bool = True):
        if holder["window"] is None and create:
            log.info("Construction de la fenetre principale")
            w = MainWindow(controller)
            w.closing_to_tray.connect(lambda: release_timer.start())
            w.quit_requested.connect(quit_app)
            w.closing_to_tray.connect(
                lambda: tray.notify(
                    "Wallpaper Studio continue en arriere-plan. "
                    "Le planificateur reste actif.",
                    "info",
                )
            )
            holder["window"] = w
        return holder["window"]

    def discard_window():
        """Detruit l'interface restee masquee, pour rendre sa memoire."""
        w = holder["window"]
        if w is None or w.isVisible():
            return
        if not controller.settings.get("liberer_interface_en_arriere_plan", True):
            return
        log.info("Interface liberee (fenetre fermee depuis un moment)")
        w.release()
        holder["window"] = None
        w.deleteLater()
        # La destruction est differee par Qt : on rend la memoire ensuite.
        from wallpaper_studio.system.memory import trim_working_set

        QTimer.singleShot(1500, lambda: trim_working_set("interface liberee"))

    def open_window():
        release_timer.stop()
        w = get_window()
        w.showNormal()
        w.raise_()
        w.activateWindow()

    # --- Zone de notification ---
    tray.show_window.connect(open_window)
    tray.toggle_pause.connect(
        lambda: (
            controller.perf.force_resume() if controller.engine.is_paused
            else controller.engine.pause_all("demande depuis la zone de notification")
        )
    )
    tray.toggle_scheduler.connect(
        lambda: controller.scheduler.set_enabled(not controller.scheduler.enabled)
    )

    def quit_app():
        log.info("Fermeture demandee par l'utilisateur")
        tray.hide()
        controller.shutdown()
        existing = get_window(create=False)
        if existing is not None:
            existing.force_quit()
        app.quit()

    release_timer.timeout.connect(discard_window)
    tray.quit_requested.connect(quit_app)
    app.aboutToQuit.connect(controller.shutdown)

    controller.notify.connect(tray.notify)

    if not controller.start():
        QMessageBox.critical(
            get_window(create=False), APP_NAME,
            "Impossible de preparer la couche de fond d'ecran de Windows.\n\n"
            "Verifiez que l'Explorateur Windows est bien demarre, "
            "puis relancez l'application.",
        )

    if tray.is_available:
        tray.show()
    else:
        log.warning("Zone de notification indisponible sur ce systeme")

    start_minimized = args.minimized or bool(
        controller.settings.get("demarrer_minimise", False)
    )
    if start_minimized and tray.is_available:
        log.info("Demarrage dans la zone de notification, sans interface")
        tray.notify(f"{APP_NAME} est demarre en arriere-plan.", "info")
    else:
        get_window().show()

    # Recherche de mise a jour, un peu apres le demarrage pour ne pas ralentir
    # l'ouverture ni saturer une connexion qui se reveille.
    if controller.settings.get("verifier_maj_au_demarrage", True):
        def verifier_maj():
            fenetre = get_window(create=False)
            if fenetre is None:
                # En arriere-plan : on verifie sans construire l'interface,
                # et on previent par une notification seulement si besoin.
                from wallpaper_studio.system import updater

                release, erreur = updater.check_for_update()
                if release is not None:
                    tray.notify(
                        f"Wallpaper Studio {release.version} est disponible. "
                        "Ouvrez l'application pour l'installer.",
                        "info",
                    )
                elif erreur:
                    log.info("Recherche de mise a jour : %s", erreur)
            else:
                fenetre.check_for_updates(manuel=False)

        QTimer.singleShot(8000, verifier_maj)

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
