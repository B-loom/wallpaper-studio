"""Controleur de l'application : relie base, moteur, planificateur et interface.

Point d'attention : le planificateur tourne dans son propre fil, alors que le
moteur manipule des widgets Qt, qui doivent etre touches uniquement depuis le
fil de l'interface. La demande du planificateur transite donc par un signal Qt
(:attr:`AppController.schedule_apply_requested`), connecte en mode file
d'attente. C'est ce qui garantit que l'application d'un fond a 22h00 se fait
sans risque, meme si la fenetre est fermee.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from PySide6.QtCore import QObject, Qt, QTimer, Signal

from .data.models import HistoryEntry, MonitorConfig, ScheduleRule
from .data.repositories import Repositories
from .data.settings import Settings
from .engine.playback import EffectConfig, ImageAdjustments, PlaybackRequest
from .engine.wallpaper_engine import WallpaperEngine
from .media.probe import probe_media
from .media.types import FillMode, MediaKind
from .perf.performance_manager import PerformanceManager
from .scheduler.rules import ConflictPolicy
from .scheduler.scheduler import SchedulerService
from .system.monitors import MonitorManager
from .system.mouse import MouseTracker

log = logging.getLogger(__name__)


class AppController(QObject):
    """Objet central, independant de la fenetre principale.

    L'interface peut etre fermee et rouverte sans que l'etat du moteur ou du
    planificateur soit perdu.
    """

    #: (cle_ecran, media_id, regle) emis depuis le fil du planificateur.
    schedule_apply_requested = Signal(str, int, object)
    #: (message, type) pour les notifications de l'interface.
    notify = Signal(str, str)
    #: Emis apres une application de fond par le planificateur.
    state_changed = Signal()

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)

        self.settings = Settings()
        self.repos = Repositories()
        self.monitors = MonitorManager()

        self.engine = WallpaperEngine(
            monitor_manager=self.monitors,
            hardware_decode=self.settings.hardware_decode,
            fps_cap=self.settings.fps_cap,
        )
        self.perf = PerformanceManager(self.engine, self.settings)

        self.scheduler = SchedulerService(
            repos=self.repos,
            applier=self._scheduler_applier,
            monitor_keys_provider=self._managed_monitor_keys,
            policy=ConflictPolicy(self.settings.get("politique_conflit", "priority")),
        )
        self.scheduler.set_enabled(bool(self.settings.get("planification_active", True)))

        # Connexion en file d'attente : le slot s'execute dans le fil Qt.
        self.schedule_apply_requested.connect(
            self._apply_from_scheduler, Qt.QueuedConnection
        )

        # Suivi du curseur : uniquement quand un contenu interactif est actif.
        self._mouse = MouseTracker()
        self._mouse.moved.connect(self.engine.set_mouse_position)
        self.engine.wallpaper_applied.connect(lambda _: self._sync_mouse_tracking())

        # Surveillance des changements d'ecrans (branchement, resolution).
        self._monitor_watch = QTimer(self)
        # Un branchement d'ecran est rare : une verification toutes les
        # 10 s suffit et divise par deux les reveils du processus.
        self._monitor_watch.setInterval(10000)
        self._monitor_watch.timeout.connect(self._poll_monitors)

    # --- Demarrage / arret -------------------------------------------------
    def start(self) -> bool:
        """Demarre moteur, planificateur et surveillance."""
        if not self.engine.start():
            self.notify.emit(
                "La couche de fond d'ecran de Windows n'a pas pu etre preparee.",
                "erreur",
            )
            return False

        if self.settings.get("verifier_fichiers_au_demarrage", True):
            missing = self.repos.media.refresh_missing_flags()
            if missing:
                self.notify.emit(
                    f"{len(missing)} fichier(s) de la bibliotheque introuvable(s).",
                    "alerte",
                )

        self.restore_wallpapers()
        self.perf.start()
        self.scheduler.start()
        self._monitor_watch.start()
        log.info("Application demarree")
        return True

    def shutdown(self) -> None:
        """Arrete proprement tous les sous-systemes."""
        log.info("Arret de l'application")
        self._monitor_watch.stop()
        self._mouse.stop()
        self.scheduler.stop()
        self.perf.stop()
        self.engine.shutdown()
        self.repos.close()

    def _sync_mouse_tracking(self) -> None:
        """Active le suivi du curseur seulement si un fond s'en sert.

        Interroger la position du curseur en permanence serait du gaspillage :
        on ne le fait que si un effet « halo » ou un fond web est affiche.
        """
        needed = False
        for state in self.engine.screens.values():
            if state.request is None:
                continue
            if state.request.kind is MediaKind.WEB:
                needed = True
                break
            if any(e.name == "halo_souris" for e in state.request.active_effects):
                needed = True
                break
        if needed and not self._mouse.is_running:
            self._mouse.start()
        elif not needed and self._mouse.is_running:
            self._mouse.stop()

    # --- Restauration ------------------------------------------------------
    def restore_wallpapers(self) -> int:
        """Reapplique les fonds enregistres pour chaque ecran.

        Appelee au demarrage : l'etat visible d'avant la fermeture est retabli
        sans attendre la prochaine transition horaire.
        """
        restored = 0
        for monitor in self.monitors.monitors:
            config = self.repos.monitors.get(monitor.key)
            if config is None or not config.enabled or config.media_id is None:
                continue
            if self.apply_media(monitor.key, config.media_id, reason="restauration"):
                restored += 1
        if restored:
            log.info("%s fond(s) restaure(s) au demarrage", restored)
        return restored

    # --- Construction d'une demande de lecture -----------------------------
    def _managed_monitor_keys(self) -> list:
        """Ecrans que l'utilisateur a choisi de laisser gerer a l'application."""
        keys = []
        for monitor in self.monitors.monitors:
            config = self.repos.monitors.get(monitor.key)
            if config is None or config.enabled:
                keys.append(monitor.key)
        return keys

    def build_request(
        self,
        monitor_key: str,
        media_id: int,
        rule: Optional[ScheduleRule] = None,
        adjustments: Optional[ImageAdjustments] = None,
        fill_mode: Optional[FillMode] = None,
        effects: Optional[tuple] = None,
    ) -> Optional[PlaybackRequest]:
        """Assemble une demande de lecture a partir de la base et des reglages.

        L'ordre de priorite est : parametres explicites, puis reglages de la
        regle horaire, puis reglages de l'ecran, puis reglages globaux.
        """
        media = self.repos.media.get(media_id)
        if media is None:
            log.error("Media %s introuvable en base", media_id)
            return None

        config = self._monitor_config(monitor_key)

        kind = media.kind
        if kind is MediaKind.UNKNOWN:
            info = probe_media(media.path)
            kind = info.kind
            if kind is MediaKind.UNKNOWN:
                log.error("Type de media indetermine : %s", media.path)
                return None

        chosen_fill = fill_mode or (rule.fill_mode if rule and rule.fill_mode else None)
        chosen_fill = chosen_fill or config.fill_mode

        volume = rule.volume if rule and rule.volume is not None else config.volume
        muted = rule.muted if rule and rule.muted is not None else config.muted

        return PlaybackRequest(
            path=media.path,
            kind=kind,
            fill_mode=chosen_fill,
            volume=volume,
            muted=muted,
            loop=True,
            speed=config.speed,
            adjustments=adjustments if adjustments is not None else config.adjustments,
            effects=tuple(effects) if effects is not None else tuple(config.effects),
            fps_cap=self.settings.fps_cap,
            media_id=media.id,
        )

    def _monitor_config(self, monitor_key: str):
        """Reglages d'un ecran, initialises depuis les valeurs globales.

        Un ecran jamais configure herite du volume et du mode muet definis dans
        la page Parametres, au lieu de valeurs figees dans le code.
        """
        existing = self.repos.monitors.get(monitor_key)
        if existing is not None:
            return existing
        monitor = self.monitors.by_key(monitor_key)
        config = MonitorConfig(
            monitor_key=monitor_key,
            device=monitor.device if monitor else None,
            friendly_name=monitor.name if monitor else None,
            volume=int(self.settings.get("volume_global", 0)),
            muted=bool(self.settings.get("muet_global", True)),
        )
        self.repos.monitors.save(config)
        return config

    # --- Application d'un fond ---------------------------------------------
    def apply_media(
        self,
        monitor_key: str,
        media_id: int,
        rule: Optional[ScheduleRule] = None,
        reason: str = "manuel",
        adjustments: Optional[ImageAdjustments] = None,
        fill_mode: Optional[FillMode] = None,
        effects: Optional[tuple] = None,
        record_history: bool = True,
    ) -> bool:
        """Applique un fond sur un ecran et met la base a jour."""
        request = self.build_request(
            monitor_key, media_id, rule, adjustments, fill_mode, effects
        )
        if request is None:
            return False

        if not self.engine.apply(monitor_key, request):
            return False

        self.repos.monitors.set_media(monitor_key, media_id)
        self.repos.media.mark_used(media_id)

        if record_history and reason != "restauration":
            media = self.repos.media.get(media_id)
            self.repos.history.add(
                HistoryEntry(
                    occurred_at=datetime.now(),
                    monitor_key=monitor_key,
                    media_id=media_id,
                    media_title=media.title if media else None,
                    reason=reason,
                    rule_id=rule.id if rule else None,
                    rule_name=rule.name if rule else None,
                )
            )
        # Un choix manuel ne doit pas etre ecrase a la passe suivante du
        # planificateur : on lui indique que cet ecran porte deja ce media.
        if reason == "manuel":
            self.scheduler.forget_applied(monitor_key)
        self.state_changed.emit()
        return True

    def apply_to_all(self, media_id: int) -> int:
        count = 0
        for key in self._managed_monitor_keys():
            if self.apply_media(key, media_id, reason="manuel"):
                count += 1
        return count

    def apply_span(self, media_id: int) -> int:
        """Repartit une image sur tous les ecrans."""
        media = self.repos.media.get(media_id)
        if media is None:
            return 0
        if media.kind is MediaKind.VIDEO:
            self.notify.emit(
                "Le mode panoramique ne gere que les images fixes pour l'instant.",
                "alerte",
            )
            return 0
        request = self.build_request(
            self.monitors.monitors[0].key if self.monitors.monitors else "", media_id
        )
        if request is None:
            return 0
        count = self.engine.apply_span(request)
        if count:
            for key in self._managed_monitor_keys():
                self.repos.monitors.set_media(key, media_id)
            self.repos.media.mark_used(media_id)
            self.state_changed.emit()
        return count

    def restore_previous(self, monitor_key: str) -> bool:
        config = self.repos.monitors.get(monitor_key)
        if config is None or config.previous_media_id is None:
            self.notify.emit("Aucun fond precedent memorise pour cet ecran.", "info")
            return False
        return self.apply_media(
            monitor_key, config.previous_media_id, reason="retour arriere"
        )

    # --- Planificateur -----------------------------------------------------
    def _scheduler_applier(
        self, monitor_key: str, media_id: Optional[int], rule: Optional[ScheduleRule]
    ) -> bool:
        """Appele depuis le fil du planificateur : ne touche pas a Qt.

        On se contente d'emettre un signal ; l'application reelle a lieu dans
        :meth:`_apply_from_scheduler`, cote interface. On repond ``True`` car
        la demande a bien ete transmise ; un echec eventuel est journalise et
        provoque une nouvelle tentative au cycle suivant via
        :meth:`SchedulerService.forget_applied`.
        """
        if media_id is None:
            return False
        self.schedule_apply_requested.emit(monitor_key, media_id, rule)
        return True

    def _apply_from_scheduler(
        self, monitor_key: str, media_id: int, rule: Optional[ScheduleRule]
    ) -> None:
        ok = self.apply_media(
            monitor_key, media_id, rule=rule, reason="planificateur",
            record_history=False,  # le planificateur ecrit deja l'historique
        )
        if not ok:
            log.error(
                "Application planifiee en echec (ecran %s, media %s)",
                monitor_key, media_id,
            )
            # Oublier l'etat force une nouvelle tentative au prochain cycle.
            self.scheduler.forget_applied(monitor_key)
            media = self.repos.media.get(media_id)
            self.notify.emit(
                f"Le fond programme « {media.title if media else media_id} » "
                "n'a pas pu etre applique.",
                "erreur",
            )

    # --- Ecrans ------------------------------------------------------------
    def _poll_monitors(self) -> None:
        """Detecte un branchement ou un changement de resolution."""
        if self.engine.refresh_monitors():
            self.scheduler.notify_monitors_changed()
            self.restore_wallpapers()
            self.state_changed.emit()

    def notify_resume_from_sleep(self) -> None:
        """A appeler au reveil de veille."""
        self.engine.refresh_monitors()
        self.scheduler.notify_resume_from_sleep()

    # --- Reglages ----------------------------------------------------------
    def save_monitor_config(self, config: MonitorConfig) -> None:
        self.repos.monitors.save(config)
        state = self.engine.state_for(config.monitor_key)
        if state and state.request:
            # Reapplique a chaud les reglages (cadrage, volume, vitesse).
            request = state.request.with_(
                fill_mode=config.fill_mode,
                volume=config.volume,
                muted=config.muted,
                speed=config.speed,
            )
            self.engine.apply(config.monitor_key, request)
