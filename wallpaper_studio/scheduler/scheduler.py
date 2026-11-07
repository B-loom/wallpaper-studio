"""Planificateur : applique les regles horaires en arriere-plan.

Principes de fiabilite
----------------------
* **Etat compare, pas compte a rebours.** A chaque reveil, le planificateur
  recalcule le fond attendu pour chaque ecran et le compare a l'etat reellement
  applique. Un compte a rebours seul derive apres une mise en veille ou un
  changement d'heure ; comparer des etats est insensible a ces aleas.
* **Reveil adaptatif.** Le minuteur vise la prochaine transition, mais ne dort
  jamais plus de :data:`MAX_SLEEP_SECONDS`. Cela garantit une verification
  reguliere meme si le systeme a dormi entre-temps.
* **Detection des sauts d'horloge.** Si le temps ecoule reel s'ecarte fortement
  du delai demande (veille, changement d'heure, correction NTP), on reevalue
  immediatement.
* **Instance unique.** :meth:`SchedulerService.start` est sans effet si le
  planificateur tourne deja : impossible de lancer deux boucles concurrentes.
* **Pas de changement inutile.** Un fond deja applique n'est jamais reapplique,
  ce qui evite les coupures visibles toutes les minutes.

L'horloge est injectable (parametre ``clock``) afin que les tests puissent
simuler plusieurs journees en quelques millisecondes.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from ..data.models import HistoryEntry, ScheduleRule
from ..data.repositories import Repositories
from .rules import ConflictPolicy, ScheduleDecision, next_transition, resolve_all

log = logging.getLogger(__name__)

#: Duree maximale d'un sommeil, meme si la prochaine transition est lointaine.
#: Garantit une reevaluation reguliere apres une veille prolongee.
MAX_SLEEP_SECONDS = 60.0

#: Au-dela de cet ecart entre le sommeil demande et le temps reellement ecoule,
#: on considere que l'horloge a saute (veille, changement d'heure).
CLOCK_JUMP_TOLERANCE = 30.0

Clock = Callable[[], datetime]

#: Signature de l'application d'un fond : (cle_ecran, media_id, regle) -> bool
Applier = Callable[[str, Optional[int], Optional[ScheduleRule]], bool]


class SchedulerService:
    """Boucle de planification, executee dans un fil dedie."""

    def __init__(
        self,
        repos: Repositories,
        applier: Applier,
        monitor_keys_provider: Callable[[], Sequence[str]],
        clock: Optional[Clock] = None,
        policy: ConflictPolicy = ConflictPolicy.PRIORITY,
    ):
        self._repos = repos
        self._applier = applier
        self._monitor_keys = monitor_keys_provider
        self._clock: Clock = clock or datetime.now
        self._policy = policy

        self._thread: Optional[threading.Thread] = None
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._lock = threading.RLock()

        self._enabled = True
        self._suspended_until: Optional[datetime] = None
        #: Dernier media applique par ecran, pour eviter les reapplications.
        self._applied: Dict[str, Optional[int]] = {}
        self._last_evaluation: Optional[datetime] = None
        self._next_transition: Optional[Tuple[datetime, Dict[str, ScheduleDecision]]] = None
        #: Appele apres chaque evaluation ; l'interface s'y raccroche.
        self.on_evaluated: Optional[Callable[[], None]] = None

    # --- Proprietes --------------------------------------------------------
    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def policy(self) -> ConflictPolicy:
        return self._policy

    @policy.setter
    def policy(self, value: ConflictPolicy) -> None:
        with self._lock:
            self._policy = value
        self.request_evaluation()

    @property
    def suspended_until(self) -> Optional[datetime]:
        return self._suspended_until

    @property
    def is_suspended(self) -> bool:
        if self._suspended_until is None:
            return False
        if self._clock() >= self._suspended_until:
            self._suspended_until = None
            return False
        return True

    @property
    def is_active(self) -> bool:
        """Vrai si les regles sont effectivement appliquees en ce moment."""
        return self._enabled and not self.is_suspended

    @property
    def last_evaluation(self) -> Optional[datetime]:
        return self._last_evaluation

    def next_change(self) -> Optional[Tuple[datetime, Dict[str, ScheduleDecision]]]:
        """Prochaine transition prevue, telle que calculee a la derniere passe."""
        return self._next_transition

    # --- Cycle de vie ------------------------------------------------------
    def start(self) -> bool:
        """Demarre la boucle. Sans effet si elle tourne deja."""
        with self._lock:
            if self.is_running:
                log.debug("Planificateur deja actif, demarrage ignore")
                return False
            self._stop.clear()
            self._thread = threading.Thread(
                target=self._run, name="wallpaper-scheduler", daemon=True
            )
            self._thread.start()
            log.info("Planificateur demarre")
            return True

    def stop(self, timeout: float = 3.0) -> None:
        """Arrete la boucle et attend la fin du fil."""
        with self._lock:
            thread = self._thread
            if thread is None:
                return
            self._stop.set()
            self._wake.set()
        thread.join(timeout=timeout)
        with self._lock:
            self._thread = None
        log.info("Planificateur arrete")

    def set_enabled(self, enabled: bool) -> None:
        """Active ou desactive la planification (mode automatique / manuel)."""
        self._enabled = enabled
        log.info("Planification %s", "activee" if enabled else "desactivee")
        self.request_evaluation()

    def suspend_until(self, moment: Optional[datetime]) -> None:
        """Suspend temporairement les regles jusqu'a l'instant indique."""
        self._suspended_until = moment
        if moment:
            log.info("Planification suspendue jusqu'a %s", moment.strftime("%H:%M"))
        else:
            log.info("Suspension levee")
        self.request_evaluation()

    def request_evaluation(self) -> None:
        """Demande une reevaluation immediate (reveil du fil)."""
        self._wake.set()

    def notify_resume_from_sleep(self) -> None:
        """A appeler au reveil de veille : l'etat attendu a pu changer."""
        log.info("Sortie de veille detectee, reevaluation du planificateur")
        self.request_evaluation()

    def notify_monitors_changed(self) -> None:
        """A appeler lors d'un branchement ou debranchement d'ecran."""
        with self._lock:
            # On oublie l'etat applique des ecrans disparus pour que le
            # rebranchement reapplique bien le fond attendu.
            keys = set(self._monitor_keys())
            self._applied = {k: v for k, v in self._applied.items() if k in keys}
        self.request_evaluation()

    def forget_applied(self, monitor_key: Optional[str] = None) -> None:
        """Oublie l'etat applique afin de forcer une reapplication."""
        with self._lock:
            if monitor_key is None:
                self._applied.clear()
            else:
                self._applied.pop(monitor_key, None)

    # --- Boucle ------------------------------------------------------------
    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.evaluate()
            except Exception:  # noqa: BLE001 - la boucle ne doit jamais mourir
                log.exception("Erreur pendant l'evaluation du planificateur")

            delay = self._sleep_duration()
            before = self._clock()
            self._wake.clear()
            woken = self._wake.wait(timeout=delay)
            if self._stop.is_set():
                break

            if not woken:
                elapsed = (self._clock() - before).total_seconds()
                if abs(elapsed - delay) > CLOCK_JUMP_TOLERANCE:
                    log.info(
                        "Saut d'horloge detecte (%.0f s attendues, %.0f s ecoulees)",
                        delay, elapsed,
                    )

    def _sleep_duration(self) -> float:
        """Delai avant le prochain reveil, borne par :data:`MAX_SLEEP_SECONDS`."""
        upcoming = self._next_transition
        if not upcoming:
            return MAX_SLEEP_SECONDS
        seconds = (upcoming[0] - self._clock()).total_seconds()
        if seconds <= 0:
            return 0.5
        return max(0.5, min(MAX_SLEEP_SECONDS, seconds))

    # --- Evaluation --------------------------------------------------------
    def _load_rules(self) -> List[ScheduleRule]:
        return self._repos.schedule.list(enabled_only=True)

    def evaluate(self, moment: Optional[datetime] = None) -> Dict[str, ScheduleDecision]:
        """Recalcule l'etat attendu et applique les differences.

        Retourne l'etat attendu par ecran. Methode publique : les tests
        l'appellent directement avec une horloge simulee, sans fil d'execution.
        """
        now = moment or self._clock()
        self._last_evaluation = now

        keys = list(self._monitor_keys())
        if not keys:
            self._next_transition = None
            return {}

        rules = self._load_rules()
        decisions = resolve_all(rules, keys, now, self._policy)
        self._next_transition = next_transition(rules, keys, now, self._policy)

        if self.is_active:
            for key in keys:
                self._apply_if_needed(key, decisions[key], now)

        if self.on_evaluated:
            try:
                self.on_evaluated()
            except Exception:  # noqa: BLE001
                log.exception("Erreur dans le rappel on_evaluated")
        return decisions

    def _apply_if_needed(
        self, monitor_key: str, decision: ScheduleDecision, moment: datetime
    ) -> None:
        """Applique le fond attendu si l'ecran n'y est pas deja."""
        target = decision.media_id
        if target is None:
            # Aucune regle active : on laisse le fond courant en place plutot
            # que de noircir l'ecran, ce qui serait surprenant.
            return

        with self._lock:
            already = self._applied.get(monitor_key)
        if already == target:
            return

        ok = False
        try:
            ok = self._applier(monitor_key, target, decision.rule)
        except Exception:  # noqa: BLE001
            log.exception(
                "Application du fond %s sur %s impossible", target, monitor_key
            )

        if not ok:
            # On ne memorise pas un echec : la prochaine passe reessaiera.
            log.warning(
                "Le fond %s n'a pas pu etre applique sur %s", target, monitor_key
            )
            return

        with self._lock:
            self._applied[monitor_key] = target

        media = self._repos.media.get(target)
        self._repos.history.add(
            HistoryEntry(
                occurred_at=moment,
                monitor_key=monitor_key,
                media_id=target,
                media_title=media.title if media else None,
                reason="planificateur",
                rule_id=decision.rule.id if decision.rule else None,
                rule_name=decision.rule_name,
            )
        )
        log.info(
            "Planificateur : %s -> %s (regle « %s »)",
            monitor_key, media.title if media else target, decision.rule_name,
        )

    # --- Informations pour l'interface ------------------------------------
    def describe_next(self) -> str:
        """Phrase resumant la prochaine transition prevue."""
        if not self._enabled:
            return "Planification desactivee"
        if self.is_suspended:
            return f"Suspendue jusqu'a {self._suspended_until.strftime('%H:%M')}"
        upcoming = self._next_transition
        if not upcoming:
            return "Aucune transition prevue"
        from .rules import describe_transition

        moment, _ = upcoming
        return (
            f"Prochaine transition a {moment.strftime('%H:%M')} "
            f"({describe_transition(self._clock(), moment)})"
        )
