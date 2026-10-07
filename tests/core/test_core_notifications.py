"""Notification engine (M6): persistence, cooldown, dedup, recovery
(docs/16 §4, docs/20 §11, docs/26 §6).

Expected numbers are hand-computed from `core/constants.py`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from custom_components.smart_compost.core.assessment import (
    Assessment,
    BinData,
    assess,
)
from custom_components.smart_compost.core.constants import (
    NOTIFY_COOLDOWN,
    NOTIFY_PERSISTENCE,
)
from custom_components.smart_compost.core.events import (
    CompostEvent,
    EventOrigin,
    EventType,
)
from custom_components.smart_compost.core.model import (
    ActionCode,
    Capability,
    MaterialAddition,
    NumericValue,
    ObservationCategory,
    Provenance,
    QuantityPrecision,
    Severity,
    UserObservation,
)
from custom_components.smart_compost.core.notifications import (
    CategoryState,
    NotificationCategory,
    NotificationKind,
    Pulse,
    StateCondition,
    evaluate_notifications,
    pulses_from_events,
    state_conditions,
)

NOW = datetime(2026, 10, 6, 12, 0, 0, tzinfo=UTC)


def _at(minutes: float) -> datetime:
    return NOW + timedelta(minutes=minutes)


def _condition(
    active: bool | None,
    category: NotificationCategory = NotificationCategory.MOISTURE,
    message_key: str = "moisture_too_dry",
    recovery_key: str = "resolved",
) -> StateCondition:
    return StateCondition(
        category=category,
        severity=Severity.SUGGESTION,
        active=active,
        confidence=60,
        message_key=message_key,
        recovery_key=recovery_key,
        reasons=("too_dry",),
        action=ActionCode.WATER_COMPOST,
    )


def _pulse(category: NotificationCategory = NotificationCategory.PHASE) -> Pulse:
    return Pulse(
        category=category,
        kind=NotificationKind.INFO,
        severity=Severity.INFO,
        confidence=55,
        message_key="phase_changed",
        reasons=("phase_changed",),
        before="mesophilic",
        after="thermophilic",
    )


# --- Persistence and deduplication -------------------------------------------


def test_state_condition_must_persist_before_notifying() -> None:
    assert NOTIFY_PERSISTENCE == timedelta(minutes=15)
    condition = _condition(True)

    sent, states = evaluate_notifications([], [condition], {}, NOW)
    assert sent == ()  # just observed: nothing yet (docs/16 §4 persistence)
    state = states[NotificationCategory.MOISTURE.value]
    assert state.since == NOW
    assert not state.notified

    sent, states = evaluate_notifications([], [condition], states, _at(14))
    assert sent == ()  # 14 min < NOTIFY_PERSISTENCE (15 min)
    assert states[NotificationCategory.MOISTURE.value].since == NOW

    sent, states = evaluate_notifications([], [condition], states, _at(15))
    assert len(sent) == 1
    notice = sent[0]
    assert notice.category is NotificationCategory.MOISTURE
    assert notice.kind is NotificationKind.ISSUE
    assert notice.severity is Severity.SUGGESTION
    assert notice.confidence == 60
    assert notice.message_key == "moisture_too_dry"
    assert notice.reasons == ("too_dry",)
    assert notice.action is ActionCode.WATER_COMPOST
    assert notice.emitted_at == _at(15)
    state = states[NotificationCategory.MOISTURE.value]
    assert state.notified
    assert state.last_sent == _at(15)


def test_active_condition_is_announced_only_once() -> None:
    condition = _condition(True)
    _, states = evaluate_notifications([], [condition], {}, NOW)
    sent, states = evaluate_notifications([], [condition], states, _at(15))
    assert len(sent) == 1

    # Deduplication: still active hours later → silence, no repeat.
    sent, states = evaluate_notifications([], [condition], states, _at(200))
    assert sent == ()
    assert (
        states[NotificationCategory.MOISTURE.value].last_sent == _at(15)
    )


def test_a_transient_wobble_vanishes_without_any_message() -> None:
    # Active, then gone before it matured: no issue, no recovery — the
    # sensor oscillation of docs/16 §7 produces absolute silence.
    _, states = evaluate_notifications([], [_condition(True)], {}, NOW)
    sent, states = evaluate_notifications(
        [], [_condition(False)], states, _at(5)
    )
    assert sent == ()
    assert states[NotificationCategory.MOISTURE.value] == CategoryState()

    # …and the next activation starts its persistence clock from zero.
    _, states = evaluate_notifications([], [_condition(True)], states, _at(10))
    assert states[NotificationCategory.MOISTURE.value].since == _at(10)


def test_persistence_clock_restarts_after_a_wobble() -> None:
    _, states = evaluate_notifications([], [_condition(True)], {}, NOW)
    _, states = evaluate_notifications([], [_condition(False)], states, _at(5))
    _, states = evaluate_notifications([], [_condition(True)], states, _at(10))

    sent, states = evaluate_notifications([], [_condition(True)], states, _at(20))
    assert sent == ()  # only 10 of the required 15 minutes elapsed
    sent, states = evaluate_notifications([], [_condition(True)], states, _at(25))
    assert len(sent) == 1


# --- Recovery ----------------------------------------------------------------


def test_recovery_follows_an_announced_issue() -> None:
    _, states = evaluate_notifications([], [_condition(True)], {}, NOW)
    sent, states = evaluate_notifications([], [_condition(True)], states, _at(15))
    assert len(sent) == 1

    sent, states = evaluate_notifications(
        [], [_condition(False)], states, _at(20)
    )
    assert len(sent) == 1
    recovery = sent[0]
    assert recovery.kind is NotificationKind.RECOVERY
    assert recovery.severity is Severity.INFO  # a recovery is not an alarm
    assert recovery.message_key == "resolved"
    assert recovery.emitted_at == _at(20)
    state = states[NotificationCategory.MOISTURE.value]
    assert not state.notified
    assert state.since is None
    assert state.last_sent == _at(20)


def test_recovery_carries_a_category_specific_message_key() -> None:
    condition = _condition(
        True,
        category=NotificationCategory.SENSOR,
        message_key="sensor_unavailable",
        recovery_key="sensor_restored",
    )
    _, states = evaluate_notifications([], [condition], {}, NOW)
    _, states = evaluate_notifications([], [condition], states, _at(15))
    deactivated = _condition(
        False, NotificationCategory.SENSOR, recovery_key="sensor_restored"
    )
    sent, states = evaluate_notifications(
        [], [deactivated], states, _at(20)
    )
    assert len(sent) == 1
    assert sent[0].message_key == "sensor_restored"
    assert sent[0].kind is NotificationKind.RECOVERY


def test_cooldown_gates_reactivation_after_a_recovery() -> None:
    _, states = evaluate_notifications([], [_condition(True)], {}, NOW)
    _, states = evaluate_notifications([], [_condition(True)], states, _at(15))
    _, states = evaluate_notifications([], [_condition(False)], states, _at(16))

    # Reactivated right away: persistence restarts, and the cooldown from
    # the recovery still holds.
    _, states = evaluate_notifications([], [_condition(True)], states, _at(20))
    sent, states = evaluate_notifications(
        [], [_condition(True)], states, _at(35)
    )
    assert sent == ()  # 19 min < NOTIFY_COOLDOWN since the recovery

    later = _at(16) + NOTIFY_COOLDOWN
    sent, states = evaluate_notifications([], [_condition(True)], states, later)
    assert len(sent) == 1  # mature AND past the cooldown


# --- Unknown never fabricates ------------------------------------------------


def test_unknown_condition_emits_nothing_and_keeps_memory() -> None:
    _, states = evaluate_notifications([], [_condition(True)], {}, NOW)
    _, states = evaluate_notifications([], [_condition(True)], states, _at(15))
    remembered = states[NotificationCategory.MOISTURE.value]
    assert remembered.notified

    # The measurement went UNKNOWN: not a recovery, not a re-announce.
    sent, states = evaluate_notifications([], [_condition(None)], states, _at(30))
    assert sent == ()
    assert states[NotificationCategory.MOISTURE.value] == remembered

    # Unknown with no memory: no empty state entries are invented.
    sent, states = evaluate_notifications([], [_condition(None)], {}, NOW)
    assert sent == () and states == {}


# --- Pulses ------------------------------------------------------------------


def test_pulse_fires_immediately_but_respects_the_cooldown() -> None:
    pulse = _pulse()
    sent, states = evaluate_notifications([pulse], [], {}, NOW)
    assert len(sent) == 1
    assert sent[0].message_key == "phase_changed"
    assert sent[0].before == "mesophilic"
    assert sent[0].after == "thermophilic"
    assert sent[0].emitted_at == NOW

    # Same transition flapping an hour later: suppressed (docs/16 §7).
    sent, states = evaluate_notifications([pulse], [], states, _at(60))
    assert sent == ()

    sent, _ = evaluate_notifications(
        [pulse], [], states, _at(60) + NOTIFY_COOLDOWN
    )
    assert len(sent) == 1  # allowed again once the cooldown elapsed


def test_pulse_and_condition_categories_do_not_collide() -> None:
    phase = _pulse(NotificationCategory.PHASE)
    moisture = _condition(True)
    _, states = evaluate_notifications([phase], [moisture], {}, NOW)
    sent, states = evaluate_notifications([phase], [moisture], states, _at(15))
    # The moisture issue matures even though the phase pulse already spoke.
    assert [item.category for item in sent] == [NotificationCategory.MOISTURE]


# --- Builders: state conditions from the assessment --------------------------


def _moisture_data(value: float) -> BinData:
    return BinData(
        capabilities=frozenset(
            {Capability.MANUAL_DATA, Capability.INTERNAL_MOISTURE}
        ),
        internal_moisture=NumericValue(
            value=value,
            unit="%",
            provenance=Provenance.MEASURED,
            timestamp=NOW,
        ),
    )


def _by_category(
    previous: BinData | None, current: BinData, assessment: Assessment
) -> dict[NotificationCategory, StateCondition]:
    return {
        item.category: item
        for item in state_conditions(previous, current, assessment)
    }


def _material(kind: str) -> MaterialAddition:
    return MaterialAddition(
        timestamp=NOW,
        material_type=kind,
        quantity_value=None,
        quantity_unit=None,
        quantity_precision=QuantityPrecision.QUALITATIVE,
    )


def test_moisture_condition_maps_the_measured_band() -> None:
    dry_data = _moisture_data(25.0)
    conditions = _by_category(None, dry_data, assess(dry_data, NOW))
    moisture = conditions[NotificationCategory.MOISTURE]
    assert moisture.active is True
    assert moisture.message_key == "moisture_too_dry"
    assert moisture.action is ActionCode.WATER_COMPOST
    assert moisture.severity is Severity.SUGGESTION
    assert moisture.reasons == ("too_dry",)

    # No moisture sensor: no claim, ever — UNKNOWN is not an issue (docs/04).
    unknown = assess(BinData(), NOW)
    conditions = _by_category(None, BinData(), unknown)
    assert conditions[NotificationCategory.MOISTURE].active is None
    assert conditions[NotificationCategory.AERATION].active is None
    assert conditions[NotificationCategory.BALANCE].active is None


def test_balance_and_aeration_conditions_follow_their_domains() -> None:
    green_data = BinData(
        material_additions=(
            _material("food_scraps"),
            _material("grass_clippings"),
            _material("coffee_grounds"),
        )
    )
    conditions = _by_category(None, green_data, assess(green_data, NOW))
    balance = conditions[NotificationCategory.BALANCE]
    assert balance.active is True
    assert balance.message_key == "balance_greens"
    assert balance.action is ActionCode.ADD_BROWNS

    sour_data = BinData(
        observations=(
            UserObservation(
                timestamp=NOW,
                category=ObservationCategory.ODOR,
                value="sour smell",
            ),
        )
    )
    conditions = _by_category(None, sour_data, assess(sour_data, NOW))
    aeration = conditions[NotificationCategory.AERATION]
    assert aeration.active is True
    assert aeration.message_key == "aeration"
    assert aeration.action is ActionCode.IMPROVE_AERATION


def test_diagnostic_conditions_track_the_findings() -> None:
    rising_history = tuple(
        NumericValue(
            value=30.0 + (120 - minutes_ago) * 0.1,
            unit="°C",
            provenance=Provenance.MEASURED,
            timestamp=NOW - timedelta(minutes=minutes_ago),
        )
        for minutes_ago in (120, 100, 80, 60, 40, 20, 0)
    )
    data = BinData(
        capabilities=frozenset(
            {Capability.MANUAL_DATA, Capability.INTERNAL_TEMPERATURE}
        ),
        internal_temperature=NumericValue(
            value=42.0,
            unit="°C",
            provenance=Provenance.MEASURED,
            timestamp=NOW,
        ),
        temperature_history=rising_history,
    )
    assessment = assess(data, NOW)
    conditions = {c.category: c for c in state_conditions(None, data, assessment)}
    heating = conditions[NotificationCategory.RAPID_HEATING]
    assert heating.active is True
    assert heating.confidence == 70  # fast_rise + elevated_now
    assert "fast_rise" in heating.reasons
    assert conditions[NotificationCategory.RAPID_COOLING].active is False


def test_sensor_condition_requires_a_before_side() -> None:
    bound = BinData(
        capabilities=frozenset({Capability.INTERNAL_TEMPERATURE}),
        internal_temperature=NumericValue(
            value=40.0, unit="°C", provenance=Provenance.MEASURED, timestamp=NOW
        ),
    )
    unbound = BinData(capabilities=frozenset({Capability.MANUAL_DATA}))
    assessment = assess(unbound, NOW)

    def sensor_state(previous: BinData | None, current: BinData):
        return next(
            c
            for c in state_conditions(previous, current, assessment)
            if c.category is NotificationCategory.SENSOR
        )

    # A bin that never had a sensor must never be told it is down.
    assert sensor_state(None, unbound).active is None
    assert sensor_state(unbound, unbound).active is None
    assert sensor_state(unbound, bound).active is False
    assert sensor_state(bound, unbound).active is True
    assert sensor_state(bound, bound).active is False
    recovery = sensor_state(bound, unbound)
    assert recovery.recovery_key == "sensor_restored"
    assert recovery.severity is Severity.SUGGESTION


# --- Builders: pulses from events ---------------------------------------------


def _event(event_type: EventType, **kwargs) -> CompostEvent:
    return CompostEvent(
        timestamp=NOW, type=event_type, origin=EventOrigin.INTEGRATION, **kwargs
    )


def _thermophilic_assessment():
    history = tuple(
        NumericValue(
            value=55.0,
            unit="°C",
            provenance=Provenance.MEASURED,
            timestamp=NOW - timedelta(minutes=minutes_ago),
        )
        for minutes_ago in (240, 180, 120, 60, 30, 0)
    )
    data = BinData(
        capabilities=frozenset(
            {Capability.MANUAL_DATA, Capability.INTERNAL_TEMPERATURE}
        ),
        internal_temperature=NumericValue(
            value=55.0,
            unit="°C",
            provenance=Provenance.MEASURED,
            timestamp=NOW,
        ),
        temperature_history=history,
    )
    return assess(data, NOW)


def test_phase_pulses_pick_category_and_confidence() -> None:
    assessment = _thermophilic_assessment()
    pulses = pulses_from_events(
        [_event(EventType.PHASE_CHANGED, before_state="mesophilic",
                after_state="thermophilic")],
        assessment,
    )
    assert len(pulses) == 1
    pulse = pulses[0]
    assert pulse.category is NotificationCategory.THERMOPHILIC
    assert pulse.message_key == "thermophilic"
    assert pulse.kind is NotificationKind.INFO
    assert pulse.confidence == assessment.phase.confidence

    # Becoming UNKNOWN is missing evidence, not news (docs/06 §13).
    assert (
        pulses_from_events(
            [_event(EventType.PHASE_CHANGED, before_state="mesophilic",
                    after_state="unknown")],
            assessment,
        )
        == ()
    )

    # A different phase uses the generic category and the triade's confidence.
    other = pulses_from_events(
        [_event(EventType.PHASE_CHANGED, before_state="unknown",
                after_state="cooling")],
        assessment,
    )
    assert other[0].category is NotificationCategory.PHASE
    assert other[0].confidence == assessment.confidence


def test_health_pulse_direction_decodes_kind_and_severity() -> None:
    assessment = assess(BinData(), NOW)
    degraded, recovered = pulses_from_events(
        [
            _event(EventType.HEALTH_CHANGED, before_state="good",
                   after_state="fair", reason="score_70_50"),
            _event(EventType.HEALTH_CHANGED, before_state="fair",
                   after_state="good", reason="score_50_70"),
        ],
        assessment,
    )
    assert degraded.category is NotificationCategory.HEALTH
    assert degraded.kind is NotificationKind.ISSUE
    assert degraded.severity is Severity.SUGGESTION
    assert degraded.message_key == "health_degraded"
    assert degraded.reasons == ("score_70_50",)

    assert recovered.kind is NotificationKind.RECOVERY
    assert recovered.severity is Severity.INFO
    assert recovered.message_key == "health_recovered"


def test_only_worthwhile_events_become_pulses() -> None:
    assessment = assess(BinData(), NOW)
    cycle = pulses_from_events(
        [_event(EventType.CYCLE_STARTED, before_state="new",
                after_state="active", reason="first_material_logged")],
        assessment,
    )
    assert cycle[0].category is NotificationCategory.CYCLE
    assert cycle[0].kind is NotificationKind.INFO

    # Diagnostics are conditions (persistence + recovery), and a logged
    # intervention needs no notification — so neither becomes a pulse.
    assert pulses_from_events(
        [_event(EventType.RAPID_HEATING, after_state="rapid_heating")],
        assessment,
    ) == ()
    assert pulses_from_events(
        [_event(EventType.WATERING, reason="watering")], assessment
    ) == ()
    assert pulses_from_events(
        [_event(EventType.TEMPERATURE_PEAK, after_state="60.0")], assessment
    ) == ()


def test_maturity_pulse_announces_a_new_readiness() -> None:
    assessment = assess(BinData(), NOW)
    pulses = pulses_from_events(
        [_event(EventType.MATURITY_ESTIMATED, before_state="unknown",
                after_state="likely_mature")],
        assessment,
    )
    assert len(pulses) == 1
    pulse = pulses[0]
    assert pulse.category is NotificationCategory.MATURITY
    assert pulse.kind is NotificationKind.INFO
    assert pulse.message_key == "maturity_estimated"
    assert pulse.before == "unknown"
    assert pulse.after == "likely_mature"
    # This assessment knows no readiness of its own, so the confidence is
    # the assessment's — never a maturity confidence that does not exist.
    assert pulse.confidence == assessment.confidence

    # Going UNKNOWN is missing evidence, not news (docs/04).
    assert (
        pulses_from_events(
            [_event(EventType.MATURITY_ESTIMATED,
                    before_state="ready_for_curing",
                    after_state="unknown")],
            assessment,
        )
        == ()
    )
