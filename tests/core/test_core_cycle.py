"""Cycle reports, comparison and baselines (M7, docs/11, docs/18).

Expected numbers are hand-computed from `core/constants.py`: the report
window only counts records inside the cycle, thermal facts come from the
bounded series, and a baseline does not exist below BASELINE_MIN_CYCLES.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

from custom_components.smart_compost.core.assessment import assess
from custom_components.smart_compost.core.constants import (
    BASELINE_CONFIDENCE_STEP,
    BASELINE_MAX_CYCLES,
    BASELINE_MIN_CYCLES,
    MAX_STORED_CYCLES,
)
from custom_components.smart_compost.core.cycle import (
    CycleReport,
    bounded_cycles,
    build_baseline,
    build_comparison,
    build_report,
    select_previous,
    select_report,
)
from custom_components.smart_compost.core.model import (
    BinData,
    Cycle,
    CycleStatus,
    Intervention,
    InterventionType,
    MaterialAddition,
    NumericValue,
    ObservationCategory,
    Output,
    Provenance,
    QuantityPrecision,
    UserObservation,
)

NOW = datetime(2026, 10, 6, 12, 0, 0, tzinfo=UTC)


def _material(
    at: datetime,
    kind: str = "food_scraps",
    value: float | None = None,
    unit: str | None = None,
) -> MaterialAddition:
    return MaterialAddition(
        timestamp=at,
        material_type=kind,
        quantity_value=value,
        quantity_unit=unit,
        quantity_precision=(
            QuantityPrecision.EXACT
            if value is not None
            else QuantityPrecision.QUALITATIVE
        ),
    )


def _observation(at: datetime) -> UserObservation:
    return UserObservation(
        timestamp=at,
        category=ObservationCategory.MOISTURE,
        value="damp",
    )


def _intervention(at: datetime) -> Intervention:
    return Intervention(timestamp=at, type=InterventionType.TURNING)


def _reading(value: float, at: datetime) -> NumericValue:
    return NumericValue(
        value=value,
        unit="°C",
        provenance=Provenance.MEASURED,
        timestamp=at,
    )


def _completed(
    cycle_id: str,
    started: datetime,
    completed: datetime,
) -> Cycle:
    return Cycle(
        id=cycle_id,
        started_at=started,
        status=CycleStatus.COMPLETED,
        completed_at=completed,
    )


# --- Report window -----------------------------------------------------------


def test_report_counts_only_records_inside_the_cycle_window() -> None:
    """Records outside [started, completed] belong to another time."""
    started = NOW - timedelta(hours=4)
    cycle = Cycle(
        id="cycle_inside",
        started_at=started,
        status=CycleStatus.COMPLETED,
        completed_at=NOW,
    )
    data = BinData(
        material_additions=(
            _material(NOW - timedelta(hours=6), "old_leaves"),
            _material(NOW - timedelta(hours=3)),
            _material(NOW - timedelta(hours=1)),
            _material(NOW + timedelta(minutes=10), "next_batch"),
        ),
        observations=(
            _observation(NOW - timedelta(hours=2)),
            _observation(NOW - timedelta(hours=6)),
        ),
        interventions=(
            _intervention(NOW - timedelta(hours=1)),
            _intervention(NOW + timedelta(minutes=20)),
        ),
    )

    report = build_report(cycle, data, NOW)

    assert report.material_count == 2
    assert report.observation_count == 1
    assert report.intervention_count == 1
    # 4 hours = 0.1667 days → 0.2 (no false precision).
    assert report.duration_days == 0.2
    assert report.status is CycleStatus.COMPLETED
    assert report.completed_at == NOW
    assert report.output is None
    # No temperature history at all: an explicit limitation, never a number.
    assert report.temperature_samples == 0
    assert report.peak_temperature is None
    assert report.thermophilic_hours is None
    assert report.limitations == ("no_temperature_data",)


def test_report_thermal_facts_come_from_the_windowed_series() -> None:
    """Samples before/after the window are never borrowed (docs/11 §7)."""
    started = NOW - timedelta(hours=4)
    cycle = _completed("cycle_thermal", started, NOW)
    data = BinData(
        temperature_history=(
            _reading(30.0, NOW - timedelta(hours=5)),  # before the cycle
            _reading(30.0, started),
            _reading(50.0, NOW - timedelta(hours=3)),
            _reading(60.0, NOW - timedelta(hours=2)),
            _reading(40.0, NOW - timedelta(hours=1)),
            _reading(35.0, NOW),
            _reading(55.0, NOW + timedelta(minutes=30)),  # after completion
        )
    )

    report = build_report(cycle, data, NOW)

    assert report.temperature_samples == 5
    assert report.peak_temperature == 60.0
    # Time above 40 °C: 1800 s rising + 3600 s + 3600 s falling to 40
    # (the 40 → 35 leg contributes 0) = 9000 s = 2.5 h.
    assert report.thermophilic_hours == 2.5
    assert report.limitations == ()


def test_long_cycle_flags_the_bounded_window() -> None:
    """The series keeps 14 days: older parts of a long cycle are missing."""
    started = NOW - timedelta(days=20)
    cycle = _completed("cycle_long", started, NOW)
    data = BinData(temperature_history=(_reading(50.0, NOW - timedelta(days=1)),))

    report = build_report(cycle, data, NOW)

    assert report.duration_days == 20.0
    assert report.temperature_samples == 1
    assert report.peak_temperature == 50.0
    assert "temperature_partial_window" in report.limitations


def test_report_sums_material_quantities_per_unit_inside_the_window() -> None:
    """Amounts add up per unit inside the window; units never mix
    (docs/11 §7 quantità materiali)."""
    started = NOW - timedelta(hours=4)
    cycle = _completed("cycle_qty", started, NOW)
    data = BinData(
        material_additions=(
            _material(NOW - timedelta(hours=3), value=2.0, unit="kg"),
            _material(NOW - timedelta(hours=1), value=1.5, unit="kg"),
            _material(NOW - timedelta(hours=2), value=3.0, unit="litre"),
            # Outside the window: never borrowed.
            _material(NOW - timedelta(days=1), value=9.0, unit="kg"),
            # No amount (or a bare unit) cannot be summed.
            _material(NOW - timedelta(hours=1)),
            _material(NOW - timedelta(hours=1), unit="kg"),
        )
    )

    report = build_report(cycle, data, NOW)

    assert report.material_count == 5
    assert dict(report.material_quantity) == {"kg": 3.5, "litre": 3.0}
    assert report.material_quantity == (("kg", 3.5), ("litre", 3.0))


def test_active_cycle_window_ends_now_and_carries_the_output_of_nothing() -> None:
    cycle = Cycle(id="cycle_active", started_at=NOW - timedelta(days=2))
    report = build_report(cycle, BinData(), NOW)

    assert report.status is CycleStatus.ACTIVE
    assert report.completed_at is None
    assert report.duration_days == 2.0
    assert report.output is None
    assert report.limitations == ("no_temperature_data",)


# --- Comparison --------------------------------------------------------------


def test_comparison_deltas_are_plain_subtractions() -> None:
    current = build_report(
        _completed("b", NOW - timedelta(days=10), NOW - timedelta(days=2)),
        BinData(),
        NOW,
    )
    previous = build_report(
        _completed("a", NOW - timedelta(days=20), NOW - timedelta(days=12)),
        BinData(),
        NOW,
    )
    # Both reports share the same shape here; widen them to real numbers.
    current = replace(
        current,
        duration_days=8.0,
        material_count=12,
        intervention_count=4,
        peak_temperature=65.0,
        thermophilic_hours=12.5,
    )
    previous = replace(
        previous,
        duration_days=6.0,
        material_count=15,
        intervention_count=4,
        peak_temperature=60.0,
        thermophilic_hours=10.0,
    )

    delta = build_comparison(current, previous)

    assert delta.previous_cycle_id == "a"
    assert delta.duration_days_delta == 2.0
    assert delta.material_count_delta == -3
    assert delta.intervention_count_delta == 0
    assert delta.peak_delta == 5.0
    assert delta.thermophilic_hours_delta == 2.5


def test_comparison_never_fabricates_a_thermal_delta() -> None:
    """Unknown minus a number is still unknown (docs/04, docs/18 §10)."""
    current = build_report(
        _completed("b", NOW - timedelta(days=4), NOW),
        BinData(),
        NOW,
    )
    previous = build_report(
        _completed("a", NOW - timedelta(days=10), NOW - timedelta(days=6)),
        BinData(),
        NOW,
    )

    delta = build_comparison(current, previous)

    # Counts and durations are known on both sides…
    assert delta.material_count_delta == 0
    assert delta.duration_days_delta == 0.0
    # …thermal data is missing on BOTH sides: no delta, no fake 0.0.
    assert delta.peak_delta is None
    assert delta.thermophilic_hours_delta is None
    # …and so is any quantity: nothing logged means unknown, not 0.0.
    assert delta.material_quantity_delta is None


def test_comparison_quantity_delta_needs_the_same_unit_both_sides() -> None:
    """kg minus kg is a delta; kg minus litres or nothing is unknown."""
    def _cycle_with(
        cycle_id: str,
        started: datetime,
        completed: datetime,
        materials: tuple[MaterialAddition, ...],
    ) -> CycleReport:
        return build_report(
            _completed(cycle_id, started, completed),
            BinData(material_additions=materials),
            NOW,
        )

    same_unit = _cycle_with(
        "b",
        NOW - timedelta(days=10),
        NOW - timedelta(days=2),
        (_material(NOW - timedelta(days=3), value=4.5, unit="kg"),),
    )
    previous = _cycle_with(
        "a",
        NOW - timedelta(days=20),
        NOW - timedelta(days=12),
        (_material(NOW - timedelta(days=13), value=6.0, unit="kg"),),
    )
    assert build_comparison(same_unit, previous).material_quantity_delta == -1.5

    other_unit = _cycle_with(
        "c",
        NOW - timedelta(days=8),
        NOW - timedelta(days=1),
        (_material(NOW - timedelta(days=2), value=4.0, unit="litre"),),
    )
    assert (
        build_comparison(other_unit, previous).material_quantity_delta is None
    )

    no_quantity = _cycle_with(
        "d",
        NOW - timedelta(days=7),
        NOW - timedelta(days=1),
        (_material(NOW - timedelta(days=2)),),
    )
    assert (
        build_comparison(no_quantity, previous).material_quantity_delta is None
    )


# --- Baseline ----------------------------------------------------------------


def _baseline_report(cycle_id: str, days: float, peak: float | None) -> CycleReport:
    report = build_report(
        _completed(
            cycle_id,
            NOW - timedelta(days=days),
            NOW,
        ),
        BinData(),
        NOW,
    )
    return replace(report, duration_days=days, peak_temperature=peak)


def test_baseline_does_not_exist_below_the_minimum() -> None:
    reports = [
        _baseline_report("a", 7.0, 55.0),
        _baseline_report("b", 9.0, 60.0),
    ]
    assert build_baseline(reports) is None
    assert BASELINE_MIN_CYCLES == 3


def test_baseline_is_the_median_of_this_bins_own_completed_cycles() -> None:
    reports = [
        _baseline_report("a", 7.0, 55.0),
        _baseline_report("b", 9.0, 62.0),
        _baseline_report("c", 8.0, 60.0),
        # An active cycle is never part of a completed-cycle baseline.
        Cycle(id="active", started_at=NOW - timedelta(hours=1)),
    ]

    baseline = build_baseline(reports)

    assert baseline is not None
    assert baseline.completed_cycles == 3
    # min(3, 5) * 20 = 60.
    assert baseline.confidence == BASELINE_MIN_CYCLES * BASELINE_CONFIDENCE_STEP
    assert baseline.median_duration_days == 8.0
    # peaks 55 / 60 / 62 → median 60.0.
    assert baseline.median_peak == 60.0
    assert baseline.limitations == ()


def test_baseline_without_thermal_history_stays_honest() -> None:
    reports = [
        _baseline_report("a", 7.0, None),
        _baseline_report("b", 9.0, None),
        _baseline_report("c", 8.0, None),
    ]

    baseline = build_baseline(reports)

    assert baseline is not None
    assert baseline.median_duration_days == 8.0
    assert baseline.median_peak is None
    assert baseline.limitations == ("insufficient_thermal_cycles",)


def test_baseline_confidence_saturates_at_the_maximum() -> None:
    reports = [
        _baseline_report(f"c{index}", float(5 + index), 50.0 + index)
        for index in range(6)
    ]

    baseline = build_baseline(reports)

    assert baseline is not None
    assert baseline.completed_cycles == 6
    # min(6, BASELINE_MAX_CYCLES) * step = 100, never more.
    assert baseline.confidence == BASELINE_MAX_CYCLES * BASELINE_CONFIDENCE_STEP
    assert baseline.confidence == 100


# --- Selection ---------------------------------------------------------------


def test_select_report_prefers_the_active_cycle_else_the_latest_completed() -> None:
    early = build_report(
        _completed("early", NOW - timedelta(days=30), NOW - timedelta(days=20)),
        BinData(),
        NOW,
    )
    late = build_report(
        _completed("late", NOW - timedelta(days=20), NOW - timedelta(days=10)),
        BinData(),
        NOW,
    )
    active = build_report(
        Cycle(id="now", started_at=NOW - timedelta(hours=2)), BinData(), NOW
    )

    assert select_report(()) is None
    assert select_report((early, late)).cycle_id == "late"
    assert select_report((early, late, active)).cycle_id == "now"


def test_select_previous_only_compares_within_the_same_bin_history() -> None:
    a = build_report(
        _completed("a", NOW - timedelta(days=30), NOW - timedelta(days=20)),
        BinData(),
        NOW,
    )
    b = build_report(
        _completed("b", NOW - timedelta(days=20), NOW - timedelta(days=10)),
        BinData(),
        NOW,
    )
    active = build_report(
        Cycle(id="c", started_at=NOW - timedelta(hours=2)), BinData(), NOW
    )

    assert select_previous((), active) is None
    assert select_previous((active,), active) is None
    # The most recent OTHER cycle — not the current one.
    assert select_previous((a, b, active), active).cycle_id == "b"
    assert select_previous((a, b), b).cycle_id == "a"


# --- Retention ---------------------------------------------------------------


def test_bounded_cycles_drops_the_oldest_completed_first() -> None:
    def _many(count: int) -> tuple[Cycle, ...]:
        return tuple(
            _completed(
                f"c{index}",
                NOW - timedelta(days=count - index),
                NOW - timedelta(days=count - index - 1),
            )
            for index in range(count)
        )

    within = _many(MAX_STORED_CYCLES)
    assert bounded_cycles(within) == within

    over = _many(MAX_STORED_CYCLES + 3)
    kept = bounded_cycles(over)
    assert len(kept) == MAX_STORED_CYCLES
    # The newest survive, the oldest age out.
    assert kept[0].id == "c3"
    assert kept[-1].id == f"c{MAX_STORED_CYCLES + 2}"


def test_bounded_cycles_never_drops_the_active_cycle() -> None:
    completed = tuple(
        _completed(
            f"c{index}",
            NOW - timedelta(days=60 - index),
            NOW - timedelta(days=59 - index),
        )
        for index in range(MAX_STORED_CYCLES + 2)
    )
    active = Cycle(id="tracking", started_at=NOW - timedelta(hours=1))

    kept = bounded_cycles((*completed, active))

    assert len(kept) == MAX_STORED_CYCLES
    assert active in kept
    assert completed[0] not in kept


# --- Assessment integration --------------------------------------------------


def test_assessment_carries_report_comparison_and_baseline() -> None:
    data = BinData(
        material_additions=(_material(NOW - timedelta(days=25)),),
        cycles=(
            _completed("a", NOW - timedelta(days=30), NOW - timedelta(days=20)),
            _completed("b", NOW - timedelta(days=20), NOW - timedelta(days=10)),
            _completed("c", NOW - timedelta(days=10), NOW - timedelta(days=2)),
        ),
    )

    assessment = assess(data, NOW)

    assert assessment.cycle_report is not None
    # The selected report is the latest completed cycle (docs/11 §7).
    assert assessment.cycle_report.cycle_id == "c"
    assert assessment.cycle_comparison is not None
    assert assessment.cycle_comparison.previous_cycle_id == "b"
    assert assessment.baseline is not None
    assert assessment.baseline.completed_cycles == 3


def test_assessment_without_cycles_reports_nothing() -> None:
    assessment = assess(BinData(), NOW)

    assert assessment.cycle_report is None
    assert assessment.cycle_comparison is None
    assert assessment.baseline is None


def test_output_round_trip_through_the_report() -> None:
    output = Output(
        timestamp=NOW,
        quantity_value=40.0,
        quantity_unit="litre",
        destination="raised_bed",
        notes="sieved",
    )
    cycle = Cycle(
        id="with_output",
        started_at=NOW - timedelta(days=7),
        status=CycleStatus.COMPLETED,
        completed_at=NOW,
        output=output,
    )

    report = build_report(cycle, BinData(), NOW)

    assert report.output is not None
    assert report.output.quantity_value == 40.0
    assert report.output.destination == "raised_bed"
