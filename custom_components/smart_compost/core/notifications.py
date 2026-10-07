"""Notification engine (M6, docs/16): notify only when it helps.

Two input shapes feed one state machine (docs/16 §4):

* ``StateCondition`` — a condition that is active or not (moisture issue,
  aeration, balance, diagnostics, sensor availability). The engine only
  notifies after the condition has persisted NOTIFY_PERSISTENCE, notifies
  again only after NOTIFY_COOLDOWN, deduplicates while it stays active,
  and emits a recovery only for conditions it actually announced — an
  UNKNOWN or a short wobble is silently forgotten, never a ping-pong of
  issue/recovered (docs/16 §7).
* ``Pulse`` — a one-shot fact (phase changed, health band moved, cycle
  started). Pulses skip persistence but share the per-category cooldown.

Both are pure: the persisted ``CategoryState`` comes in, the updated state
goes out — which is what makes the cooldown survive a restart (docs/26 §6).

Built-in text is a Home Assistant concern: this module emits machine codes
only (docs/24: no hardcoded English in the engine).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum

from .assessment import Assessment
from .constants import (
    AERATION_ACTION_THRESHOLD,
    NOTIFY_COOLDOWN,
    NOTIFY_PERSISTENCE,
)
from .events import CompostEvent, EventType
from .health import AERATION_DOMAIN, BALANCE_DOMAIN, MOISTURE_DOMAIN
from .model import ActionCode, BinData, Capability, Phase, Severity

#: All machine message keys the engine can emit; strings.json's
#: ``notification`` section must contain exactly these (tested).
NOTIFICATION_MESSAGE_KEYS = frozenset(
    {
        "phase_changed",
        "thermophilic",
        "health_degraded",
        "health_recovered",
        "rapid_heating",
        "rapid_cooling",
        "moisture_too_dry",
        "moisture_too_wet",
        "aeration",
        "balance_greens",
        "balance_browns",
        "cycle_started",
        "cycle_completed",
        "maturity_estimated",
        "sensor_unavailable",
        "sensor_restored",
        "resolved",
    }
)

_BAND_RANK = {"poor": 0, "fair": 1, "good": 2}


class NotificationCategory(StrEnum):
    """Built-in notification categories (docs/16 §3 candidates).

    Each is individually enable/disable-able by the user (docs/14 §10);
    degraded/recovered and unavailable/restored are kinds WITHIN a
    category, not separate toggles.
    """

    PHASE = "phase"
    THERMOPHILIC = "thermophilic"
    HEALTH = "health"
    RAPID_HEATING = "rapid_heating"
    RAPID_COOLING = "rapid_cooling"
    MOISTURE = "moisture"
    AERATION = "aeration"
    BALANCE = "balance"
    CYCLE = "cycle"
    CYCLE_COMPLETED = "cycle_completed"
    MATURITY = "maturity"
    SENSOR = "sensor"


class NotificationKind(StrEnum):
    """What kind of message this is (docs/16 §4: recovery is explicit)."""

    ISSUE = "issue"
    RECOVERY = "recovery"
    INFO = "info"


@dataclass(frozen=True, slots=True, kw_only=True)
class CategoryState:
    """Persisted per-category engine memory (cooldown must survive restart)."""

    since: datetime | None = None
    notified: bool = False
    last_sent: datetime | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class StateCondition:
    """A condition observed now: True active, False resolved, None no claim.

    `message_key` is only read when the condition emits an ISSUE, so a
    builder may carry the key of its active variant only.
    """

    category: NotificationCategory
    severity: Severity
    active: bool | None
    confidence: int
    message_key: str
    recovery_key: str = "resolved"
    reasons: tuple[str, ...] = ()
    action: ActionCode = ActionCode.NONE


@dataclass(frozen=True, slots=True, kw_only=True)
class Pulse:
    """A one-shot notification from a detected transition."""

    category: NotificationCategory
    kind: NotificationKind
    severity: Severity
    confidence: int
    message_key: str
    reasons: tuple[str, ...] = ()
    action: ActionCode = ActionCode.NONE
    before: str | None = None
    after: str | None = None


@dataclass(frozen=True, slots=True)
class SentNotification:
    """One notification the engine decided to emit (docs/16 §5 content)."""

    category: NotificationCategory
    kind: NotificationKind
    severity: Severity
    confidence: int
    message_key: str
    reasons: tuple[str, ...]
    action: ActionCode
    emitted_at: datetime
    before: str | None = None
    after: str | None = None


def state_conditions(
    previous_data: BinData | None,
    current_data: BinData,
    assessment: Assessment,
) -> tuple[StateCondition, ...]:
    """Map the current assessment to per-category state conditions.

    UNKNOWN domains produce `active=None` — the engine must never invent a
    recovery from a missing measurement (docs/04: unknown ≠ fine).
    """
    confidence = assessment.confidence
    by_name = {result.name: result for result in assessment.health.domains}
    conditions: list[StateCondition] = []

    moisture = by_name[MOISTURE_DOMAIN]
    moisture_reason = moisture.reason_code
    conditions.append(
        StateCondition(
            category=NotificationCategory.MOISTURE,
            severity=Severity.SUGGESTION,
            active=(
                None
                if moisture.score is None or moisture_reason is None
                else moisture_reason in ("too_dry", "too_wet")
            ),
            confidence=confidence,
            message_key=(
                "moisture_too_wet"
                if moisture_reason == "too_wet"
                else "moisture_too_dry"
            ),
            reasons=(moisture_reason,) if moisture_reason else (),
            action=(
                ActionCode.WATER_COMPOST
                if moisture_reason == "too_dry"
                else ActionCode.ADD_BROWNS
            ),
        )
    )

    aeration = by_name[AERATION_DOMAIN]
    conditions.append(
        StateCondition(
            category=NotificationCategory.AERATION,
            severity=Severity.SUGGESTION,
            active=(
                None
                if aeration.score is None
                else aeration.score < AERATION_ACTION_THRESHOLD
            ),
            confidence=confidence,
            message_key="aeration",
            reasons=(aeration.reason_code,) if aeration.reason_code else (),
            action=ActionCode.IMPROVE_AERATION,
        )
    )

    balance = by_name[BALANCE_DOMAIN]
    balance_reason = balance.reason_code
    conditions.append(
        StateCondition(
            category=NotificationCategory.BALANCE,
            severity=Severity.SUGGESTION,
            active=(
                None
                if balance.score is None or balance_reason is None
                else balance_reason
                in ("greens_without_browns", "browns_without_greens")
            ),
            confidence=confidence,
            message_key=(
                "balance_browns"
                if balance_reason == "browns_without_greens"
                else "balance_greens"
            ),
            reasons=(balance_reason,) if balance_reason else (),
            action=(
                ActionCode.ADD_GREENS
                if balance_reason == "browns_without_greens"
                else ActionCode.ADD_BROWNS
            ),
        )
    )

    for code, category in (
        ("rapid_heating", NotificationCategory.RAPID_HEATING),
        ("rapid_cooling", NotificationCategory.RAPID_COOLING),
    ):
        finding = next((d for d in assessment.diagnostics if d.code == code), None)
        conditions.append(
            StateCondition(
                category=category,
                severity=Severity.SUGGESTION,
                active=finding is not None,
                confidence=finding.confidence if finding else confidence,
                message_key=code,
                reasons=finding.signals if finding else (),
            )
        )

    # Sensor availability needs the "before" side: a bin that simply has no
    # sensor must never be told its sensor is down (docs/16 §7, PR-001).
    current_bound = Capability.INTERNAL_TEMPERATURE in current_data.capabilities
    if current_bound:
        sensor_active: bool | None = False
    elif previous_data is None:
        sensor_active = None
    elif Capability.INTERNAL_TEMPERATURE in previous_data.capabilities:
        sensor_active = True
    else:
        sensor_active = None
    conditions.append(
        StateCondition(
            category=NotificationCategory.SENSOR,
            severity=Severity.SUGGESTION,
            active=sensor_active,
            confidence=confidence,
            message_key="sensor_unavailable",
            recovery_key="sensor_restored",
            reasons=("internal_temperature_missing",),
        )
    )

    return tuple(conditions)


def pulses_from_events(
    events: Sequence[CompostEvent], assessment: Assessment
) -> tuple[Pulse, ...]:
    """Turn detected transitions into one-shot notifications.

    Only transitions worth telling a human become pulses: rapid heating
    and cooling are conditions (they carry persistence and recovery), and
    logged actions need no notification — the user just performed them.
    """
    pulses: list[Pulse] = []
    for event in events:
        if event.type is EventType.PHASE_CHANGED:
            if event.after_state is None or event.after_state == "unknown":
                # Going UNKNOWN is missing evidence, not news (docs/06 §13).
                continue
            thermophilic = event.after_state == Phase.THERMOPHILIC.value
            phase_matches = (
                assessment.phase.phase is not None
                and assessment.phase.phase.value == event.after_state
            )
            pulses.append(
                Pulse(
                    category=(
                        NotificationCategory.THERMOPHILIC
                        if thermophilic
                        else NotificationCategory.PHASE
                    ),
                    kind=NotificationKind.INFO,
                    severity=Severity.INFO,
                    confidence=(
                        assessment.phase.confidence
                        if phase_matches
                        else assessment.confidence
                    ),
                    message_key=(
                        "thermophilic" if thermophilic else "phase_changed"
                    ),
                    reasons=("phase_changed",),
                    before=event.before_state,
                    after=event.after_state,
                )
            )
        elif event.type is EventType.HEALTH_CHANGED:
            before_rank = _BAND_RANK.get(event.before_state or "")
            after_rank = _BAND_RANK.get(event.after_state or "")
            if before_rank is None or after_rank is None:
                continue
            worsened = after_rank < before_rank
            pulses.append(
                Pulse(
                    category=NotificationCategory.HEALTH,
                    kind=(
                        NotificationKind.ISSUE
                        if worsened
                        else NotificationKind.RECOVERY
                    ),
                    severity=(
                        Severity.SUGGESTION if worsened else Severity.INFO
                    ),
                    confidence=assessment.confidence,
                    message_key=(
                        "health_degraded" if worsened else "health_recovered"
                    ),
                    reasons=(event.reason,) if event.reason else (),
                    before=event.before_state,
                    after=event.after_state,
                )
            )
        elif event.type is EventType.MATURITY_ESTIMATED:
            if event.after_state is None or event.after_state == "unknown":
                # "Not ready yet" is missing evidence, not news (docs/04).
                continue
            maturity_matches = (
                assessment.maturity.state is not None
                and assessment.maturity.state.value == event.after_state
            )
            pulses.append(
                Pulse(
                    category=NotificationCategory.MATURITY,
                    kind=NotificationKind.INFO,
                    severity=Severity.INFO,
                    confidence=(
                        assessment.maturity.confidence
                        if maturity_matches
                        else assessment.confidence
                    ),
                    message_key="maturity_estimated",
                    reasons=("readiness_changed",),
                    before=event.before_state,
                    after=event.after_state,
                )
            )
        elif event.type in (EventType.CYCLE_STARTED, EventType.CYCLE_COMPLETED):
            completed = event.type is EventType.CYCLE_COMPLETED
            pulses.append(
                Pulse(
                    category=(
                        NotificationCategory.CYCLE_COMPLETED
                        if completed
                        else NotificationCategory.CYCLE
                    ),
                    kind=NotificationKind.INFO,
                    severity=Severity.INFO,
                    confidence=assessment.confidence,
                    message_key=(
                        "cycle_completed" if completed else "cycle_started"
                    ),
                    reasons=(event.reason,) if event.reason else (),
                    before=event.before_state,
                    after=event.after_state,
                )
            )
    return tuple(pulses)


def evaluate_notifications(
    pulses: Sequence[Pulse],
    conditions: Sequence[StateCondition],
    states: Mapping[str, CategoryState],
    now: datetime,
) -> tuple[tuple[SentNotification, ...], dict[str, CategoryState]]:
    """Run the anti-fatigue state machine once (docs/16 §4).

    Returns what to emit plus the updated persisted state. Deterministic:
    same inputs → same outputs, no clock, no globals (docs/24).
    """
    emitted: list[SentNotification] = []
    updated: dict[str, CategoryState] = dict(states)

    for condition in conditions:
        key = condition.category.value
        state = updated.get(key, CategoryState())
        if condition.active is None:
            # No claim either way: memory untouched. Unknown never counts
            # as recovered (docs/04).
            continue

        if condition.active:
            if state.since is None:
                state = replace(state, since=now)
            if not state.notified:
                mature = (now - state.since) >= NOTIFY_PERSISTENCE
                if mature and _cooldown_ok(state, now):
                    emitted.append(
                        SentNotification(
                            category=condition.category,
                            kind=NotificationKind.ISSUE,
                            severity=condition.severity,
                            confidence=condition.confidence,
                            message_key=condition.message_key,
                            reasons=condition.reasons,
                            action=condition.action,
                            emitted_at=now,
                        )
                    )
                    state = replace(state, notified=True, last_sent=now)
        elif state.notified:
            # Recovery only for announced issues, and it restarts the
            # cooldown: the classic flap can send at most one message per
            # NOTIFY_COOLDOWN window.
            emitted.append(
                SentNotification(
                    category=condition.category,
                    kind=NotificationKind.RECOVERY,
                    severity=Severity.INFO,
                    confidence=condition.confidence,
                    message_key=condition.recovery_key,
                    reasons=condition.reasons,
                    action=ActionCode.NONE,
                    emitted_at=now,
                )
            )
            state = replace(state, notified=False, since=None, last_sent=now)
        elif state.since is not None:
            # Ended before it matured: a transient wobble vanishes without
            # a single message (docs/16 §7: no noise).
            state = replace(state, since=None)
        else:
            continue  # nothing remembered yet — no empty entries
        updated[key] = state

    for pulse in pulses:
        key = pulse.category.value
        state = updated.get(key, CategoryState())
        if not _cooldown_ok(state, now):
            continue  # flapping transition suppressed by the cooldown
        emitted.append(
            SentNotification(
                category=pulse.category,
                kind=pulse.kind,
                severity=pulse.severity,
                confidence=pulse.confidence,
                message_key=pulse.message_key,
                reasons=pulse.reasons,
                action=pulse.action,
                emitted_at=now,
                before=pulse.before,
                after=pulse.after,
            )
        )
        updated[key] = replace(state, last_sent=now)

    return tuple(emitted), updated


def _cooldown_ok(state: CategoryState, now: datetime) -> bool:
    """True when this category may speak again (docs/16 §4 cooldown)."""
    if state.last_sent is None:
        return True
    return (now - state.last_sent) >= NOTIFY_COOLDOWN
