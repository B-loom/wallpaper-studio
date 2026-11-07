"""Economies de ressources et mesures de performance.

Le gestionnaire observe periodiquement l'etat du systeme (fenetre de premier
plan, alimentation, verrouillage de session) et met les rendus en pause quand
ils ne servent a rien. Il expose aussi les mesures affichees dans la page
Performances.

Honnetete des mesures : seules les valeurs reellement obtenues sont publiees.
La charge GPU, par exemple, n'est pas accessible sans pilote ou bibliotheque
dediee ; le champ correspondant vaut alors ``None`` et l'interface affiche un
tiret.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from PySide6.QtCore import QObject, QTimer, Signal

from ..system.foreground import ForegroundInfo, foreground_info
from ..system.power import PowerStatus, is_session_locked, power_status

log = logging.getLogger(__name__)

try:
    import psutil

    PSUTIL_AVAILABLE = True
except ImportError:  # pragma: no cover
    PSUTIL_AVAILABLE = False

#: Raisons possibles d'une mise en pause automatique.
REASON_FULLSCREEN = "application en plein ecran"
REASON_MAXIMIZED = "fenetre maximisee"
REASON_BATTERY = "fonctionnement sur batterie"
REASON_LOCKED = "session verrouillee"

#: Periode de verification des conditions de pause, fenetre visible/masquee.
WATCH_INTERVAL_VISIBLE = 2000
WATCH_INTERVAL_HIDDEN = 5000


@dataclass
class PerformanceSnapshot:
    """Mesures instantanees. ``None`` = donnee non disponible sur ce systeme."""

    #: Memoire de travail du processus, en mega-octets.
    ram_mb: Optional[float] = None
    #: Part de processeur consommee par l'application, en pourcent.
    cpu_percent: Optional[float] = None
    #: Charge processeur globale du systeme, en pourcent.
    system_cpu_percent: Optional[float] = None
    #: Charge GPU : non mesurable sans bibliotheque dediee, donc toujours None.
    gpu_percent: Optional[float] = None
    #: Cadence par ecran, telle que rapportee par chaque moteur de rendu.
    fps_by_screen: Dict[str, Optional[float]] = field(default_factory=dict)
    active_wallpapers: int = 0
    animated_wallpapers: int = 0
    paused: bool = False
    pause_reason: Optional[str] = None
    power: Optional[PowerStatus] = None
    threads: Optional[int] = None

    @property
    def ram_text(self) -> str:
        return f"{self.ram_mb:.0f} Mo" if self.ram_mb is not None else "-"

    @property
    def cpu_text(self) -> str:
        return f"{self.cpu_percent:.1f} %" if self.cpu_percent is not None else "-"

    @property
    def system_cpu_text(self) -> str:
        return (
            f"{self.system_cpu_percent:.0f} %"
            if self.system_cpu_percent is not None else "-"
        )

    @property
    def gpu_text(self) -> str:
        # Mesure non disponible : on l'indique clairement plutot que d'afficher 0.
        return "non mesuree"

    @property
    def fps_text(self) -> str:
        values = [v for v in self.fps_by_screen.values() if v]
        if not values:
            return "-"
        return " / ".join(f"{v:.0f}" for v in values)


class PerformanceManager(QObject):
    """Surveille le systeme et pilote les mises en pause automatiques."""

    #: Emis a chaque nouveau releve.
    snapshot_ready = Signal(object)
    #: (en_pause, raison)
    auto_pause_changed = Signal(bool, str)

    def __init__(self, engine, settings, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._engine = engine
        self._settings = settings
        self._process = psutil.Process(os.getpid()) if PSUTIL_AVAILABLE else None
        self._auto_paused = False
        self._pause_reason: Optional[str] = None
        self._last_snapshot = PerformanceSnapshot()

        # Premiere mesure de cpu_percent : la valeur initiale est toujours 0,
        # on l'amorce des maintenant pour que le premier releve soit utile.
        if self._process is not None:
            try:
                self._process.cpu_percent(interval=None)
            except Exception:  # noqa: BLE001
                pass

        # Surveillance des conditions de pause : indispensable en permanence,
        # mais ralentie quand l'interface est masquee.
        self._watch = QTimer(self)
        self._watch.setInterval(WATCH_INTERVAL_VISIBLE)
        self._watch.timeout.connect(self._check_conditions)

        # Releve de mesures : utile uniquement quand la page Performances est
        # affichee. psutil n'est donc plus interroge en arriere-plan.
        self._measure = QTimer(self)
        self._measure.setInterval(2000)
        self._measure.timeout.connect(self._collect)
        self._measuring = False

    # --- Cycle de vie ------------------------------------------------------
    def start(self) -> None:
        self._watch.start()
        log.info(
            "Gestionnaire de performances demarre (psutil %s)",
            "disponible" if PSUTIL_AVAILABLE else "absent",
        )

    def stop(self) -> None:
        self._watch.stop()
        self._measure.stop()
        self._measuring = False

    # --- Pilotage depuis l'interface ---------------------------------------
    def set_measuring(self, active: bool) -> None:
        """Active le releve de mesures, reserve a la page Performances."""
        if active == self._measuring:
            return
        self._measuring = active
        if active:
            self._collect()
            self._measure.start()
        else:
            self._measure.stop()
        log.debug("Releve de performances : %s", "actif" if active else "arrete")

    def set_ui_visible(self, visible: bool) -> None:
        """Ralentit la surveillance quand la fenetre est masquee.

        Une reaction en 5 s au lieu de 2 s suffit largement pour mettre les
        fonds en pause au lancement d'un jeu, et divise d'autant le nombre de
        reveils du processus.
        """
        self._watch.setInterval(
            WATCH_INTERVAL_VISIBLE if visible else WATCH_INTERVAL_HIDDEN
        )
        if not visible:
            self.set_measuring(False)

    @property
    def auto_paused(self) -> bool:
        return self._auto_paused

    @property
    def pause_reason(self) -> Optional[str]:
        return self._pause_reason

    @property
    def last_snapshot(self) -> PerformanceSnapshot:
        return self._last_snapshot

    # --- Regles de mise en pause -------------------------------------------
    def _pause_reason_now(self) -> Optional[str]:
        """Determine s'il faut suspendre les rendus, et pourquoi."""
        settings = self._settings

        if settings.get("pause_si_session_verrouillee", True) and is_session_locked():
            return REASON_LOCKED

        info: Optional[ForegroundInfo] = foreground_info()
        if info is not None:
            if settings.get("pause_si_jeu_plein_ecran", True) and info.should_pause_fullscreen:
                return REASON_FULLSCREEN
            if settings.get("pause_si_fenetre_maximisee", False) and info.should_pause_maximized:
                return REASON_MAXIMIZED

        if settings.get("pause_si_batterie", True):
            status = power_status()
            if status.on_battery:
                return REASON_BATTERY

        return None

    def _check_conditions(self) -> None:
        try:
            reason = self._pause_reason_now()
        except Exception:  # noqa: BLE001 - une sonde systeme ne doit rien casser
            log.exception("Evaluation des conditions de pause impossible")
            return

        if reason and not self._auto_paused:
            self._auto_paused = True
            self._pause_reason = reason
            self._engine.pause_all(reason)
            # Les fonds sont suspendus : c'est le bon moment pour rendre au
            # systeme la memoire que l'application n'utilise plus.
            from ..system.memory import trim_working_set

            trim_working_set(f"pause : {reason}")
            self.auto_pause_changed.emit(True, reason)
        elif not reason and self._auto_paused:
            self._auto_paused = False
            self._pause_reason = None
            self._engine.resume_all("conditions revenues a la normale")
            self.auto_pause_changed.emit(False, "")

    def force_resume(self) -> None:
        """Reprend la lecture et oublie la pause automatique en cours."""
        self._auto_paused = False
        self._pause_reason = None
        self._engine.resume_all("reprise manuelle")

    # --- Mesures -----------------------------------------------------------
    def _collect(self) -> None:
        snapshot = self.measure()
        self._last_snapshot = snapshot
        self.snapshot_ready.emit(snapshot)

    def measure(self) -> PerformanceSnapshot:
        """Releve les mesures disponibles sur ce systeme."""
        ram = cpu = sys_cpu = threads = None
        if self._process is not None:
            try:
                ram = self._process.memory_info().rss / (1024 * 1024)
                # interval=None : mesure depuis l'appel precedent, sans bloquer.
                cpu = self._process.cpu_percent(interval=None)
                threads = self._process.num_threads()
                sys_cpu = psutil.cpu_percent(interval=None)
            except Exception as exc:  # noqa: BLE001
                log.debug("Mesure de performance indisponible : %s", exc)

        return PerformanceSnapshot(
            ram_mb=ram,
            cpu_percent=cpu,
            system_cpu_percent=sys_cpu,
            gpu_percent=None,  # non mesurable sans bibliotheque dediee
            fps_by_screen=self._engine.fps_report(),
            active_wallpapers=self._engine.active_count,
            animated_wallpapers=self._engine.animated_count,
            paused=self._engine.is_paused,
            pause_reason=self._pause_reason,
            power=power_status(),
            threads=threads,
        )

    # --- Profils de qualite ------------------------------------------------
    def apply_quality_profile(self, profile: str) -> None:
        """Ajuste le plafond d'images par seconde selon le profil choisi."""
        caps = {"performance": 20, "equilibre": 30, "qualite": 60}
        fps = caps.get(profile, 30)
        self._settings.set("limite_fps", fps)
        self._engine.set_fps_cap(fps)
        log.info("Profil de qualite « %s » applique (%s FPS)", profile, fps)
