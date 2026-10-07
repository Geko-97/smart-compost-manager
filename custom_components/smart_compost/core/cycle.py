"""Cycle reports, comparison and personal baselines (M7, docs/11, docs/18).

A report only counts what happened INSIDE the cycle window — records and
samples outside it belong to another time and are never borrowed. Thermal
facts come from the bounded temperature series; without sensor data they
stay None with an explicit limitation instead of a plausible number
(docs/04, docs/18 §10).

Comparison is deliberately same-bin only: bin A must never learn from bin
B unless the user builds an explicit aggregation (docs/11 §2, §8), and the
baseline is built exclusively from this bin's own completed cycles, never
below BASELINE_MIN_CYCLES (docs/18 §4).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from statistics import median

from .constants import (
    BASELINE_CONFIDENCE_STEP,
    BASELINE_MAX_CYCLES,
    BASELINE_MIN_CYCLES,
    MAX_STORED_CYCLES,
    TEMPERATURE_HISTORY_WINDOW,
)
from .model import BinData, Cycle, CycleStatus, Output
from .temperature import analyze

_SECONDS_PER_DAY = 86400.0


@dataclass(frozen=True, slots=True)
class CycleReport:
    """Facts about one cycle, bounded to its window (docs/11 §7)."""

    cycle_id: str
    status: CycleStatus
    started_at: datetime
    completed_at: datetime | None
    duration_days: float
    material_count: int
    observation_count: int
    intervention_count: int
    temperature_samples: int
    peak_temperature: float | None
    thermophilic_hours: float | None
    output: Output | None
    material_quantity: tuple[tuple[str, float], ...] = ()
    limitations: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CycleComparison:
    """Side-by-side deltas against another cycle of the SAME bin.

    A thermal delta is None when either side has no thermal data — an
    unknown minus a number is still unknown, never a fabricated delta.
    """

    previous_cycle_id: str
    duration_days_delta: float
    material_count_delta: int
    intervention_count_delta: int
    peak_delta: float | None = None
    thermophilic_hours_delta: float | None = None
    material_quantity_delta: float | None = None


@dataclass(frozen=True, slots=True)
class Baseline:
    """How this bin usually behaves, from its own completed cycles only."""

    completed_cycles: int
    confidence: int
    median_duration_days: float
    median_peak: float | None
    limitations: tuple[str, ...] = ()


def build_report(cycle: Cycle, data: BinData, now: datetime) -> CycleReport:
    """One cycle's facts from the bin's records and thermal history."""
    end = cycle.completed_at if cycle.completed_at is not None else now
    started = cycle.started_at

    material_count = sum(
        1
        for item in data.material_additions
        if started <= item.timestamp <= end
    )
    observation_count = sum(
        1 for item in data.observations if started <= item.timestamp <= end
    )
    intervention_count = sum(
        1 for item in data.interventions if started <= item.timestamp <= end
    )

    # Material amounts are summed per unit: adding kg to litres would be
    # a fabricated number, so units never mix (docs/11 §7 quantità).
    totals: dict[str, float] = {}
    for item in data.material_additions:
        if (
            started <= item.timestamp <= end
            and item.quantity_value is not None
            and item.quantity_unit
        ):
            unit = item.quantity_unit
            totals[unit] = round(totals.get(unit, 0.0) + item.quantity_value, 3)
    material_quantity = tuple(sorted(totals.items()))

    samples = tuple(
        item
        for item in data.temperature_history
        if item.timestamp is not None and started <= item.timestamp <= end
    )
    limitations: list[str] = []
    temperature_samples = 0
    peak_temperature: float | None = None
    thermophilic_hours: float | None = None
    if samples:
        analysis = analyze(samples, end)
        temperature_samples = analysis.sample_count
        peak_temperature = analysis.peak_value
        thermophilic_hours = round(
            analysis.time_above_thermophilic.total_seconds() / 3600.0, 1
        )
        if (end - started) > TEMPERATURE_HISTORY_WINDOW:
            # The series only keeps 14 days: older parts of a long cycle
            # were never observed here, and the report says so.
            limitations.append("temperature_partial_window")
    else:
        limitations.append("no_temperature_data")

    return CycleReport(
        cycle_id=cycle.id,
        status=cycle.status,
        started_at=started,
        completed_at=cycle.completed_at,
        duration_days=round((end - started).total_seconds() / _SECONDS_PER_DAY, 1),
        material_count=material_count,
        observation_count=observation_count,
        intervention_count=intervention_count,
        temperature_samples=temperature_samples,
        peak_temperature=peak_temperature,
        thermophilic_hours=thermophilic_hours,
        output=cycle.output,
        material_quantity=material_quantity,
        limitations=tuple(limitations),
    )


def build_comparison(
    current: CycleReport, previous: CycleReport
) -> CycleComparison:
    """Deltas of one cycle against another cycle of the same bin."""
    peak_delta: float | None = None
    if (
        current.peak_temperature is not None
        and previous.peak_temperature is not None
    ):
        peak_delta = round(
            current.peak_temperature - previous.peak_temperature, 1
        )
    thermophilic_delta: float | None = None
    if (
        current.thermophilic_hours is not None
        and previous.thermophilic_hours is not None
    ):
        thermophilic_delta = round(
            current.thermophilic_hours - previous.thermophilic_hours, 1
        )
    # A quantity delta needs the SAME single unit on both sides: missing
    # on either side or two different units stay unknown (docs/11 §7).
    quantity_delta: float | None = None
    current_units = dict(current.material_quantity)
    previous_units = dict(previous.material_quantity)
    if (
        len(current_units) == 1
        and len(previous_units) == 1
        and next(iter(current_units)) == next(iter(previous_units))
    ):
        unit = next(iter(current_units))
        quantity_delta = round(current_units[unit] - previous_units[unit], 3)
    return CycleComparison(
        previous_cycle_id=previous.cycle_id,
        duration_days_delta=round(
            current.duration_days - previous.duration_days, 1
        ),
        material_count_delta=current.material_count - previous.material_count,
        intervention_count_delta=(
            current.intervention_count - previous.intervention_count
        ),
        peak_delta=peak_delta,
        thermophilic_hours_delta=thermophilic_delta,
        material_quantity_delta=quantity_delta,
    )


def build_baseline(reports: Sequence[CycleReport]) -> Baseline | None:
    """This bin's usual behaviour from its own completed cycles.

    Below BASELINE_MIN_CYCLES there is no baseline at all — a couple of
    observations are an anecdote, not a pattern (docs/18 §4). The thermal
    median needs its own minimum, otherwise it stays UNKNOWN (docs/18 §10).
    """
    completed = [
        report for report in reports if report.status is CycleStatus.COMPLETED
    ]
    if len(completed) < BASELINE_MIN_CYCLES:
        return None

    peaks = sorted(
        report.peak_temperature
        for report in completed
        if report.peak_temperature is not None
    )
    median_peak = (
        round(float(median(peaks)), 1)
        if len(peaks) >= BASELINE_MIN_CYCLES
        else None
    )
    return Baseline(
        completed_cycles=len(completed),
        confidence=min(len(completed), BASELINE_MAX_CYCLES)
        * BASELINE_CONFIDENCE_STEP,
        median_duration_days=round(
            float(median([report.duration_days for report in completed])), 1
        ),
        median_peak=median_peak,
        limitations=() if median_peak is not None else (
            "insufficient_thermal_cycles",
        ),
    )


def bounded_cycles(cycles: Sequence[Cycle]) -> tuple[Cycle, ...]:
    """Keep the newest MAX_STORED_CYCLES cycles (docs/19 §10 retention).

    The oldest COMPLETED cycles age out first; an active cycle is never
    dropped — dropping the cycle the user is currently tracking would lose
    state, not just history.
    """
    if len(cycles) <= MAX_STORED_CYCLES:
        return tuple(cycles)
    actives = [cycle for cycle in cycles if cycle.status is CycleStatus.ACTIVE]
    completed = [cycle for cycle in cycles if cycle.status is not CycleStatus.ACTIVE]
    budget = max(MAX_STORED_CYCLES - len(actives), 0)
    keep = {cycle.id for cycle in actives}
    if budget:
        keep.update(cycle.id for cycle in completed[-budget:])
    return tuple(cycle for cycle in cycles if cycle.id in keep)


def select_report(
    reports: Sequence[CycleReport],
) -> CycleReport | None:
    """The report worth showing: the active cycle, else the latest one.

    Cycles are per-bin and created only by this bin's user, so the
    selection can never reach into another bin (docs/11 §2).
    """
    active = next(
        (report for report in reports if report.status is CycleStatus.ACTIVE),
        None,
    )
    if active is not None:
        return active
    completed = [
        report for report in reports if report.status is CycleStatus.COMPLETED
    ]
    if not completed:
        return None
    return max(
        completed,
        key=lambda report: report.completed_at or report.started_at,
    )


def select_previous(
    reports: Sequence[CycleReport], current: CycleReport
) -> CycleReport | None:
    """The most recent other cycle of the same bin, for comparison."""
    others = [
        report for report in reports if report.cycle_id != current.cycle_id
    ]
    if not others:
        return None
    return max(
        others,
        key=lambda report: report.completed_at or report.started_at,
    )
