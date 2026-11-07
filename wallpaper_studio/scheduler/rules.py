"""Logique des regles horaires, sans effet de bord.

Ce module ne touche ni a la base, ni a l'ecran, ni a l'horloge systeme : toutes
les fonctions prennent la date et l'heure en parametre. C'est ce qui permet de
tester les transitions (y compris celles qui traversent minuit) avec une horloge
simulee, sans attendre plusieurs heures.

Convention de plage horaire
---------------------------
Une regle est definie par ``start_minute`` et ``end_minute``, exprimes en
minutes depuis minuit. L'intervalle est **ferme a gauche, ouvert a droite** :
``[start, end[``. Ainsi deux regles 08h00-22h00 et 22h00-08h00 se succedent sans
trou ni recouvrement.

Lorsque ``end_minute <= start_minute``, la plage traverse minuit. Le masque de
jours designe alors **le jour ou la plage commence** : une regle nocturne
22h00-08h00 cochee « lundi » couvre le lundi 22h00 jusqu'au mardi 08h00.

Une regle dont ``start == end`` couvre les 24 heures du jour selectionne.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, Iterable, List, Optional, Sequence

from ..data.models import ScheduleRule

MINUTES_PER_DAY = 1440


class ConflictPolicy(str, Enum):
    """Comportement lorsque plusieurs regles s'appliquent au meme instant."""

    #: Priorite la plus elevee ; a egalite, la regle commencee le plus recemment.
    PRIORITY = "priority"
    #: La regle dont la plage a commence le plus recemment l'emporte.
    MOST_RECENT = "most_recent"
    #: La regle la plus ancienne (plus petit identifiant) l'emporte.
    OLDEST = "oldest"
    #: La plage la plus courte l'emporte : utile pour une exception ponctuelle
    #: inseree dans une plage large.
    SHORTEST = "shortest"

    @property
    def label(self) -> str:
        return {
            ConflictPolicy.PRIORITY: "Priorite la plus elevee",
            ConflictPolicy.MOST_RECENT: "Regle commencee le plus recemment",
            ConflictPolicy.OLDEST: "Regle la plus ancienne",
            ConflictPolicy.SHORTEST: "Plage la plus courte",
        }[self]


def minutes_of_day(moment: datetime) -> int:
    return moment.hour * 60 + moment.minute


def day_is_selected(mask: int, weekday: int) -> bool:
    """``weekday`` suit ``datetime.weekday()`` : 0 = lundi."""
    return bool(mask & (1 << (weekday % 7)))


def rule_is_active(rule: ScheduleRule, moment: datetime) -> bool:
    """Vrai si la regle couvre l'instant donne."""
    if not rule.enabled:
        return False
    minute = minutes_of_day(moment)
    weekday = moment.weekday()

    if rule.start_minute == rule.end_minute:
        # Plage de 24 h sur les jours coches.
        return day_is_selected(rule.days_mask, weekday)

    if rule.end_minute > rule.start_minute:
        # Plage normale, entierement dans la journee.
        return (
            day_is_selected(rule.days_mask, weekday)
            and rule.start_minute <= minute < rule.end_minute
        )

    # Plage traversant minuit : deux morceaux a tester.
    if minute >= rule.start_minute:
        # Soiree : le jour courant doit etre coche.
        return day_is_selected(rule.days_mask, weekday)
    if minute < rule.end_minute:
        # Petit matin : c'est la plage ouverte la veille qui nous couvre.
        return day_is_selected(rule.days_mask, (weekday - 1) % 7)
    return False


def rule_started_at(rule: ScheduleRule, moment: datetime) -> Optional[datetime]:
    """Instant precis ou la plage active a commence, ou ``None`` si inactive."""
    if not rule_is_active(rule, moment):
        return None
    minute = minutes_of_day(moment)
    day_start = moment.replace(hour=0, minute=0, second=0, microsecond=0)

    if rule.start_minute == rule.end_minute:
        return day_start
    if rule.end_minute > rule.start_minute:
        return day_start + timedelta(minutes=rule.start_minute)
    # Plage nocturne : commencee aujourd'hui (soiree) ou hier (petit matin).
    if minute >= rule.start_minute:
        return day_start + timedelta(minutes=rule.start_minute)
    return day_start - timedelta(days=1) + timedelta(minutes=rule.start_minute)


def applicable_rules(
    rules: Iterable[ScheduleRule], monitor_key: str, moment: datetime
) -> List[ScheduleRule]:
    """Regles actives pour un ecran donne a un instant donne.

    Une regle sans ``monitor_key`` s'applique a tous les ecrans.
    """
    return [
        r
        for r in rules
        if (r.monitor_key is None or r.monitor_key == monitor_key)
        and rule_is_active(r, moment)
    ]


def resolve_rule(
    rules: Iterable[ScheduleRule],
    monitor_key: str,
    moment: datetime,
    policy: ConflictPolicy = ConflictPolicy.PRIORITY,
) -> Optional[ScheduleRule]:
    """Regle retenue pour un ecran, conflits tranches selon ``policy``.

    Dans tous les cas, une regle visant explicitement l'ecran l'emporte sur une
    regle « tous les ecrans » de meme rang : c'est le reglage le plus precis qui
    doit gagner.
    """
    candidates = applicable_rules(rules, monitor_key, moment)
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]

    def specificity(rule: ScheduleRule) -> int:
        return 1 if rule.monitor_key is not None else 0

    def started(rule: ScheduleRule) -> datetime:
        return rule_started_at(rule, moment) or datetime.min

    if policy is ConflictPolicy.PRIORITY:
        key = lambda r: (r.priority, specificity(r), started(r), r.id or 0)  # noqa: E731
    elif policy is ConflictPolicy.MOST_RECENT:
        key = lambda r: (started(r), specificity(r), r.priority, r.id or 0)  # noqa: E731
    elif policy is ConflictPolicy.SHORTEST:
        key = lambda r: (-r.duration_minutes, specificity(r), r.priority, r.id or 0)  # noqa: E731
    else:  # OLDEST
        key = lambda r: (-(r.id or 0), specificity(r), r.priority)  # noqa: E731

    return max(candidates, key=key)


@dataclass(frozen=True)
class ScheduleDecision:
    """Ce que le planificateur attend pour un ecran a un instant donne."""

    monitor_key: str
    rule: Optional[ScheduleRule]

    @property
    def media_id(self) -> Optional[int]:
        return self.rule.media_id if self.rule else None

    @property
    def rule_name(self) -> Optional[str]:
        return self.rule.name if self.rule else None


def resolve_all(
    rules: Sequence[ScheduleRule],
    monitor_keys: Sequence[str],
    moment: datetime,
    policy: ConflictPolicy = ConflictPolicy.PRIORITY,
) -> Dict[str, ScheduleDecision]:
    """Etat attendu de tous les ecrans a un instant donne."""
    return {
        key: ScheduleDecision(key, resolve_rule(rules, key, moment, policy))
        for key in monitor_keys
    }


def _boundary_minutes(rules: Iterable[ScheduleRule]) -> List[int]:
    """Minutes de la journee ou une transition peut se produire."""
    out = {0}
    for r in rules:
        out.add(r.start_minute % MINUTES_PER_DAY)
        out.add(r.end_minute % MINUTES_PER_DAY)
    return sorted(out)


def next_transition(
    rules: Sequence[ScheduleRule],
    monitor_keys: Sequence[str],
    moment: datetime,
    policy: ConflictPolicy = ConflictPolicy.PRIORITY,
    horizon_days: int = 8,
) -> Optional[tuple]:
    """Prochain instant ou l'etat attendu change, et le nouvel etat.

    Retourne ``(instant, etats)`` ou ``None`` si rien ne change dans l'horizon.
    On n'evalue que les instants frontiere des regles : balayer minute par
    minute serait inutilement couteux, alors qu'un changement ne peut survenir
    qu'au debut ou a la fin d'une plage.

    Un horizon de 8 jours couvre le cycle hebdomadaire complet plus une marge.
    """
    if not rules or not monitor_keys:
        return None

    current = resolve_all(rules, monitor_keys, moment, policy)
    boundaries = _boundary_minutes(rules)
    base = moment.replace(hour=0, minute=0, second=0, microsecond=0)

    for day in range(horizon_days):
        for minute in boundaries:
            candidate = base + timedelta(days=day, minutes=minute)
            if candidate <= moment:
                continue
            state = resolve_all(rules, monitor_keys, candidate, policy)
            if any(
                state[k].media_id != current[k].media_id for k in monitor_keys
            ):
                return (candidate, state)
    return None


def describe_transition(moment: datetime, target: datetime) -> str:
    """Delai restant avant une transition, en francais."""
    delta = target - moment
    total = int(delta.total_seconds())
    if total < 0:
        return "maintenant"
    if total < 60:
        return f"dans {total} s"
    minutes, _ = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    if days:
        return f"dans {days} j {hours} h"
    if hours:
        return f"dans {hours} h {minutes:02d} min"
    return f"dans {minutes} min"


def validate_rule(rule: ScheduleRule) -> List[str]:
    """Messages d'erreur empechant l'enregistrement d'une regle."""
    problems: List[str] = []
    if not rule.name.strip():
        problems.append("Le nom de la regle est obligatoire.")
    if not rule.media_id:
        problems.append("Choisissez un fond d'ecran pour cette regle.")
    if not 0 <= rule.start_minute < MINUTES_PER_DAY:
        problems.append("L'heure de debut est invalide.")
    if not 0 <= rule.end_minute < MINUTES_PER_DAY:
        problems.append("L'heure de fin est invalide.")
    if rule.days_mask == 0:
        problems.append("Selectionnez au moins un jour de la semaine.")
    return problems
