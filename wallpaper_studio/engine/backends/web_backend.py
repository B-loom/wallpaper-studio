"""Fonds d'ecran HTML / CSS / JavaScript, executes dans un bac a sable.

Securite
--------
Un fond web est du code tiers. Il est donc execute avec des privileges
volontairement reduits :

* **profil ephemere** (``off-the-record``) : ni cookies, ni cache, ni stockage
  local conserves entre deux sessions ;
* **acces reseau refuse par defaut** : un intercepteur bloque toute requete
  sortant du dossier du fond d'ecran. L'utilisateur doit autoriser
  explicitement chaque fond a joindre Internet (option ``reseau`` du manifeste,
  confirmee dans l'interface) ;
* **pas d'acces aux fichiers locaux** hors de son propre dossier ;
* **ni fenetres surgissantes, ni presse-papiers, ni geolocalisation, ni camera,
  ni micro** : toutes les demandes de permission sont refusees ;
* **aucun pont JavaScript vers Python** : le fond ne peut pas piloter
  l'application.

Limites documentees
-------------------
* QtWebEngine (Chromium) consomme nettement plus de memoire qu'une image ou une
  video : comptez 120 a 250 Mo par fond web actif.
* Le son d'un fond web n'est pas reglable individuellement par l'application.
* Un fond web ne recoit pas les clics du bureau (voir
  :mod:`wallpaper_studio.system.win_desktop`) ; seule la position du curseur lui est
  transmise, via ``window.wallpaperStudio``.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtWidgets import QWidget

from ...media.types import WEB_INDEX_NAME, WEB_MANIFEST_NAME
from ..playback import PlaybackRequest, PlaybackState
from .base import WallpaperBackend

log = logging.getLogger(__name__)

try:  # QtWebEngine est optionnel : l'application fonctionne sans.
    from PySide6.QtWebEngineCore import (
        QWebEnginePage,
        QWebEngineProfile,
        QWebEngineSettings,
        QWebEngineUrlRequestInterceptor,
    )
    from PySide6.QtWebEngineWidgets import QWebEngineView

    WEBENGINE_AVAILABLE = True
except ImportError:  # pragma: no cover - depend de l'installation
    WEBENGINE_AVAILABLE = False
    QWebEngineUrlRequestInterceptor = object  # type: ignore[assignment]


class _SandboxInterceptor(QWebEngineUrlRequestInterceptor):
    """Bloque tout ce qui sort du dossier du fond d'ecran.

    Les schemas ``data:`` et ``blob:`` restent autorises : ils ne quittent pas
    la page. Le reseau n'est ouvert que si le fond a ete explicitement autorise.
    """

    def __init__(self, root: Path, allow_network: bool):
        super().__init__()
        self._root = root.resolve()
        self._allow_network = allow_network
        self.blocked_count = 0

    def interceptRequest(self, info) -> None:  # noqa: N802 - API Qt
        url = info.requestUrl()
        scheme = url.scheme()

        if scheme in ("data", "blob", "about"):
            return

        if scheme == "file":
            try:
                target = Path(url.toLocalFile()).resolve()
                target.relative_to(self._root)
                return
            except (ValueError, OSError):
                self.blocked_count += 1
                log.warning("Fond web : acces fichier refuse -> %s", url.toString())
                info.block(True)
                return

        if not self._allow_network:
            self.blocked_count += 1
            log.info("Fond web : requete reseau bloquee -> %s", url.toString()[:120])
            info.block(True)


class _SilentPage(QWebEnginePage):
    """Page qui refuse toutes les permissions et journalise la console."""

    def __init__(self, profile, parent=None):
        super().__init__(profile, parent)

    def javaScriptConsoleMessage(self, level, message, line, source):  # noqa: N802
        log.debug("Fond web [%s:%s] %s", Path(source).name if source else "?", line, message)

    def certificateError(self, error):  # noqa: N802 - API Qt
        # Un fond d'ecran ne doit jamais passer outre une erreur de certificat.
        return False

    def javaScriptAlert(self, security_origin, msg):  # noqa: N802
        log.debug("Fond web : alert() ignore (%s)", msg)

    def javaScriptConfirm(self, security_origin, msg):  # noqa: N802
        return False


class WebBackend(WallpaperBackend):
    """Moteur de rendu des fonds d'ecran web."""

    backend_name = "web"

    def __init__(self, request: PlaybackRequest, parent: Optional[QWidget] = None):
        super().__init__(request, parent)
        self._view: Optional[QWidget] = None
        self._profile = None
        self._interceptor = None
        self._manifest = {}
        if WEBENGINE_AVAILABLE:
            self._view = QWebEngineView()
        else:
            self._view = QWidget()

    def widget(self) -> QWidget:
        return self._view

    @staticmethod
    def is_available() -> bool:
        return WEBENGINE_AVAILABLE

    # --- Manifeste ---------------------------------------------------------
    def _load_manifest(self, root: Path) -> dict:
        """Lit ``wallpaper.json`` s'il existe.

        Champs reconnus : ``nom``, ``auteur``, ``description``, ``reseau``
        (booleen, demande d'acces Internet).
        """
        path = root / WEB_MANIFEST_NAME
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError) as exc:
            log.warning("Manifeste illisible (%s) : %s", path, exc)
            return {}

    # --- Cycle de vie ------------------------------------------------------
    def start(self) -> bool:
        if not WEBENGINE_AVAILABLE:
            return self._fail(
                "Les fonds web necessitent QtWebEngine, absent de cette installation"
            )

        self._set_state(PlaybackState.LOADING)
        source = Path(self._request.path)
        if source.is_dir():
            root = source
            index = source / WEB_INDEX_NAME
        else:
            root = source.parent
            index = source
        if not index.exists():
            return self._fail(f"Page introuvable : {index.name}")

        self._manifest = self._load_manifest(root)
        allow_network = bool(self._manifest.get("reseau", False))

        # Profil ephemere : rien n'est conserve d'une session a l'autre.
        self._profile = QWebEngineProfile(self._view)
        self._profile.setHttpCacheType(QWebEngineProfile.NoCache)
        self._profile.setPersistentCookiesPolicy(
            QWebEngineProfile.NoPersistentCookies
        )
        self._interceptor = _SandboxInterceptor(root, allow_network)
        self._profile.setUrlRequestInterceptor(self._interceptor)

        page = _SilentPage(self._profile, self._view)
        self._view.setPage(page)

        settings = page.settings()
        settings.setAttribute(QWebEngineSettings.LocalContentCanAccessRemoteUrls, allow_network)
        settings.setAttribute(QWebEngineSettings.LocalContentCanAccessFileUrls, False)
        settings.setAttribute(QWebEngineSettings.JavascriptCanOpenWindows, False)
        settings.setAttribute(QWebEngineSettings.JavascriptCanAccessClipboard, False)
        settings.setAttribute(QWebEngineSettings.AllowRunningInsecureContent, False)
        settings.setAttribute(QWebEngineSettings.ScreenCaptureEnabled, False)
        settings.setAttribute(QWebEngineSettings.FullScreenSupportEnabled, False)
        settings.setAttribute(QWebEngineSettings.PlaybackRequiresUserGesture, False)
        settings.setAttribute(QWebEngineSettings.ShowScrollBars, False)
        # L'acceleration materielle reste utile : Chromium retombe seul en
        # rendu logiciel si le pilote ne suit pas.
        settings.setAttribute(QWebEngineSettings.Accelerated2dCanvasEnabled, True)

        page.featurePermissionRequested.connect(self._deny_permission)
        page.loadFinished.connect(self._on_load_finished)

        self._view.setUrl(QUrl.fromLocalFile(str(index.resolve())))
        self._set_state(PlaybackState.PLAYING)
        log.info(
            "Fond web charge : %s (reseau %s)",
            index, "autorise" if allow_network else "bloque",
        )
        return True

    def _deny_permission(self, origin, feature) -> None:
        """Refuse systematiquement camera, micro, geolocalisation, notifications."""
        page = self._view.page()
        page.setFeaturePermission(origin, feature, QWebEnginePage.PermissionDeniedByUser)
        log.info("Fond web : permission refusee (%s)", feature)

    def _on_load_finished(self, ok: bool) -> None:
        if not ok:
            self._fail("Le fond web n'a pas pu etre charge")
            return
        self._inject_context()

    def _inject_context(self) -> None:
        """Expose quelques informations en lecture seule via ``window.wallpaperStudio``.

        Volontairement minimal : aucune fonction ne permet d'agir sur
        l'application ou sur le systeme.
        """
        script = """
        window.wallpaperStudio = Object.freeze({
            version: '%s',
            ecran: Object.freeze({largeur: window.innerWidth, hauteur: window.innerHeight}),
            souris: {x: 0, y: 0}
        });
        """ % ("0.1.0",)
        self._view.page().runJavaScript(script)

    def pause(self) -> None:
        """Suspend animations et minuteurs de la page."""
        if self._view and WEBENGINE_AVAILABLE:
            # Chromium met la page en veille lorsqu'elle est cachee.
            self._view.page().setLifecycleState(QWebEnginePage.LifecycleState.Frozen)
            self._set_state(PlaybackState.PAUSED)

    def resume(self) -> None:
        if self._view and WEBENGINE_AVAILABLE:
            self._view.page().setLifecycleState(QWebEnginePage.LifecycleState.Active)
            self._set_state(PlaybackState.PLAYING)

    def stop(self) -> None:
        if self._view and WEBENGINE_AVAILABLE:
            try:
                self._view.setUrl(QUrl("about:blank"))
                self._view.page().deleteLater()
            except RuntimeError:
                pass
        self._profile = None
        self._interceptor = None
        self._set_state(PlaybackState.STOPPED)

    def update_mouse(self, x: int, y: int) -> None:
        """Transmet la position du curseur au fond (interactivite a la souris)."""
        if self._view and WEBENGINE_AVAILABLE and self._state == PlaybackState.PLAYING:
            self._view.page().runJavaScript(
                f"if(window.wallpaperStudio){{window.wallpaperStudio.souris.x={int(x)};"
                f"window.wallpaperStudio.souris.y={int(y)};"
                f"window.dispatchEvent(new CustomEvent('wps-souris',"
                f"{{detail:{{x:{int(x)},y:{int(y)}}}}}));}}"
            )

    @property
    def blocked_requests(self) -> int:
        """Nombre de requetes bloquees par le bac a sable."""
        return self._interceptor.blocked_count if self._interceptor else 0
