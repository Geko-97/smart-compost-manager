"""Domain events (M6): facts on transitions, never noise (docs/10, docs/16).

Expected outcomes are hand-computed from `core/constants.py`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from custom_components.smart_compost.core.assessment import BinData, assess
from custom_components.smart_compost.core.constants import MAX_STORED_EVENTS
from custom_components.smart_compost.core.events import (
    CompostEvent,
    EventOrigin,
    EventType,
    bounded_events,
    health_band,
    intervention_event,
    material_event,
    observation_event,
    transition_events,
)
from custom_components.smart_compost.core.model import (
    Capability,
    MaterialAddition,
    MaturityState,
    NumericValue,
    Provenance,
    QuantityPrecision,
)

NOW = datetime(2026, 10, 6, 12, 0, 0, tzinfo=UTC)


def _sample(minutes_ago: float, value: float) -> NumericValue:
    return NumericValue(
        value=value,
        unit="°C",
        provenance=Provenance.MEASURED,
        timestamp=NOW - timedelta(minutes=minutes_ago),
    )


def _material() -> MaterialAddition:
    return MaterialAddition(
        timestamp=NOW,
        material_type="food_scraps",
        quantity_value=None,
        quantity_unit=None,
        quantity_precision=QuantityPrecision.QUALITATIVE,
    )


def _temperature_data(
    samples: tuple[NumericValue, ...], current: float
) -> BinData:
    return BinData(
        capabilities=frozenset(
            {Capability.MANUAL_DATA, Capability.INTERNAL_TEMPERATURE}
        ),
        internal_temperature=_sample(1.0, current),
        temperature_history=samples,
    )


def _types(events: tuple[CompostEvent, ...]) -> set[EventType]:
    return {event.type for event in events}


# --- Baseline and manual events ---------------------------------------------


def test_baseline_after_reload_fires_no_transitions() -> None:
    assessment = assess(BinData(material_additions=(_material(),)), NOW)
    assert transition_events(None, assessment, NOW, "bin_a") == ()


def test_manual_events_carry_origin_bin_and_type() -> None:
    material = material_event(NOW, "food_scraps", "kitchen", "bin_a")
    assert material.type is EventType.MATERIAL_ADDED
    assert material.origin is EventOrigin.MANUAL
    assert material.bin_id == "bin_a"
    assert material.reason == "food_scraps"
    assert material.notes == "kitchen"
    assert material.cycle_id is None  # unknown stays unknown (docs/10 §4)

    observation = observation_event(NOW, "odor", "sour smell", None, "bin_b")
    assert observation.type is EventType.OBSERVATION
    assert observation.reason == "odor:sour smell"
    assert observation.bin_id == "bin_b"

    # Documented intervention types get their own event name…
    for kind, expected in (
        ("watering", EventType.WATERING),
        ("turning", EventType.TURNING),
        ("aeration", EventType.AERATION),
        ("correction", EventType.MANUAL_CORRECTION),
    ):
        event = intervention_event(NOW, kind, None, "bin_a")
        assert event.type is expected
        assert event.origin is EventOrigin.MANUAL
        assert event.reason == kind

    # …and anything else falls back instead of inventing a type.
    fallback = intervention_event(NOW, "green_addition", None, "bin_a")
    assert fallback.type is EventType.INTERVENTION_LOGGED
    assert fallback.reason == "green_addition"


# --- Assessment transitions --------------------------------------------------


def test_first_logged_material_starts_the_cycle() -> None:
    previous = assess(BinData(), NOW)
    current = assess(BinData(material_additions=(_material(),)), NOW)

    events = transition_events(previous, current, NOW, "bin_a")
    cycle = [event for event in events if event.type is EventType.CYCLE_STARTED]
    assert len(cycle) == 1
    assert cycle[0].origin is EventOrigin.INTEGRATION
    assert cycle[0].bin_id == "bin_a"
    assert cycle[0].before_state == "new"
    assert cycle[0].after_state == "active"
    assert cycle[0].reason == "first_material_logged"


def test_phase_change_reports_before_and_after() -> None:
    mesophilic = _temperature_data(
        (_sample(360, 24.0), _sample(180, 26.0)), 25.0
    )
    thermophilic = _temperature_data(
        tuple(_sample(minutes_ago, 55.0) for minutes_ago in (240, 180, 120, 60, 30, 0)),
        55.0,
    )

    previous = assess(mesophilic, NOW)
    current = assess(thermophilic, NOW)
    assert previous.phase.phase is not None and current.phase.phase is not None

    events = transition_events(previous, current, NOW, "bin_a")
    changed = [event for event in events if event.type is EventType.PHASE_CHANGED]
    assert len(changed) == 1
    assert changed[0].before_state == "mesophilic"
    assert changed[0].after_state == "thermophilic"

    # Same assessment twice: nothing changed, nothing fires (docs/16 §7).
    assert transition_events(current, current, NOW, "bin_a") == ()


def test_losing_the_phase_is_an_event_but_missing_evidence() -> None:
    known = _temperature_data(
        (_sample(360, 24.0), _sample(180, 26.0)), 25.0
    )
    previous = assess(known, NOW)
    # Sensor gone: the live reading drops out, so the phase is UNKNOWN.
    current = assess(
        BinData(
            capabilities=frozenset({Capability.MANUAL_DATA}),
            temperature_history=known.temperature_history,
        ),
        NOW,
    )
    events = transition_events(previous, current, NOW, "bin_a")
    changed = [event for event in events if event.type is EventType.PHASE_CHANGED]
    assert len(changed) == 1
    assert changed[0].after_state == "unknown"  # honest, the event says so


def test_maturity_change_reports_the_new_readiness() -> None:
    young = assess(BinData(material_additions=(_material(),)), NOW)
    aged = assess(
        BinData(
            material_additions=(
                MaterialAddition(
                    timestamp=NOW - timedelta(days=10),
                    material_type="food_scraps",
                    quantity_value=None,
                    quantity_unit=None,
                    quantity_precision=QuantityPrecision.QUALITATIVE,
                ),
            )
        ),
        NOW,
    )
    assert young.maturity.state is None
    assert aged.maturity.state is MaturityState.READY_FOR_CURING

    events = transition_events(young, aged, NOW, "bin_a")
    changed = [
        event for event in events if event.type is EventType.MATURITY_ESTIMATED
    ]
    assert len(changed) == 1
    assert changed[0].origin is EventOrigin.INTEGRATION
    assert changed[0].bin_id == "bin_a"
    assert changed[0].before_state == "unknown"
    assert changed[0].after_state == "ready_for_curing"
    assert changed[0].reason == "readiness_changed"

    # Same assessment twice: nothing changed, nothing fires (docs/16 §7).
    assert transition_events(aged, aged, NOW, "bin_a") == ()


def test_health_band_moves_events_but_score_jitter_does_not() -> None:
    # Balance 40 (fair band) → balance 85 (good band): a real move.
    all_green = BinData(
        material_additions=(
            _material_at("food_scraps"),
            _material_at("grass_clippings"),
            _material_at("coffee_grounds"),
        )
    )
    mixed = BinData(
        material_additions=(
            _material_at("food_scraps"),
            _material_at("food_scraps"),
            _material_at("dry_leaves"),
        )
    )
    previous = assess(all_green, NOW)
    current = assess(mixed, NOW)
    assert previous.health.score == 40 and current.health.score == 85

    events = transition_events(previous, current, NOW, "bin_a")
    health = [event for event in events if event.type is EventType.HEALTH_CHANGED]
    assert len(health) == 1
    assert health[0].before_state == "fair"
    assert health[0].after_state == "good"
    assert health[0].reason == "score_40_85"

    # Jitter INSIDE one band (both "good") is noise: no event (docs/16 §7).
    cool = assess(_temperature_data(_flat_history(), 50.0), NOW)
    warm = assess(_temperature_data(_flat_history(), 60.0), NOW)
    assert cool.health.score == 90 and warm.health.score == 90
    assert _types(transition_events(cool, warm, NOW, "bin_a")) == set()


def test_unknown_health_is_never_a_transition() -> None:
    empty = assess(BinData(), NOW)
    scored = assess(
        _temperature_data(_flat_history(), 80.0), NOW
    )  # thermal 45 = "fair"
    assert empty.health.score is None
    events = transition_events(empty, scored, NOW, "bin_a")
    assert EventType.HEALTH_CHANGED not in _types(events)


def test_temperature_peak_reports_once_per_significant_crossing() -> None:
    below = _temperature_data(
        (_sample(30, 44.0), _sample(10, 44.0)), 44.0
    )
    crossing = _temperature_data(
        (_sample(30, 44.0), _sample(10, 46.0)), 46.0
    )
    events = transition_events(
        assess(below, NOW), assess(crossing, NOW), NOW, "bin_a"
    )
    peaks = [event for event in events if event.type is EventType.TEMPERATURE_PEAK]
    assert len(peaks) == 1
    assert peaks[0].before_state == "44.0"
    assert peaks[0].after_state == "46.0"

    # Already-significant peak climbing higher: reported once, not per sample.
    already = _temperature_data(
        (_sample(30, 50.0), _sample(10, 50.0)), 50.0
    )
    higher = _temperature_data(
        (_sample(30, 50.0), _sample(10, 52.0)), 52.0
    )
    events = transition_events(
        assess(already, NOW), assess(higher, NOW), NOW, "bin_a"
    )
    assert EventType.TEMPERATURE_PEAK not in _types(events)


def test_diagnostic_events_fire_on_appearance_only() -> None:
    flat = _temperature_data(
        tuple(_sample(minutes_ago, 42.0) for minutes_ago in (30, 20, 10)), 42.0
    )
    rising_history = tuple(
        _sample(minutes_ago, 30.0 + (120 - minutes_ago) * 0.1)
        for minutes_ago in (120, 100, 80, 60, 40, 20, 0)
    )
    rising = _temperature_data(rising_history, 42.0)

    previous = assess(flat, NOW)
    current = assess(rising, NOW)
    assert previous.diagnostics == () and len(current.diagnostics) == 1

    events = transition_events(previous, current, NOW, "bin_a")
    heating = [
        event for event in events if event.type is EventType.RAPID_HEATING
    ]
    assert len(heating) == 1
    assert heating[0].reason == "fast_rise+elevated_now"
    assert heating[0].after_state == "rapid_heating"

    # Already heating: no repeat (docs/16 §7 no repeated spam).
    assert transition_events(current, current, NOW, "bin_a") == ()


def test_events_are_bounded_to_the_newest() -> None:
    events = tuple(
        CompostEvent(
            timestamp=NOW + timedelta(minutes=index),
            type=EventType.OBSERVATION,
            origin=EventOrigin.MANUAL,
        )
        for index in range(MAX_STORED_EVENTS + 50)
    )
    bounded = bounded_events(events)
    assert len(bounded) == MAX_STORED_EVENTS
    assert bounded[-1].timestamp == events[-1].timestamp
    assert bounded[0].timestamp == events[-MAX_STORED_EVENTS].timestamp


def test_health_band_mapping_is_honest() -> None:
    assert health_band(None) is None
    assert health_band(0) == "poor"
    assert health_band(39) == "poor"
    assert health_band(40) == "fair"
    assert health_band(69) == "fair"
    assert health_band(70) == "good"
    assert health_band(100) == "good"


# --- helpers (declared last, used above) ------------------------------------


def _material_at(kind: str) -> MaterialAddition:
    return MaterialAddition(
        timestamp=NOW,
        material_type=kind,
        quantity_value=None,
        quantity_unit=None,
        quantity_precision=QuantityPrecision.QUALITATIVE,
    )


def _flat_history() -> tuple[NumericValue, ...]:
    return tuple(_sample(minutes_ago, 50.0) for minutes_ago in (60, 45, 30, 15, 0))
