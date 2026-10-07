"""Maturity assessment and forecast (M8, docs/07 §8–§13).

Phase says what is probably happening; maturity says how ready the material
probably is — and *for what*. A claim is never built from a single variable
(docs/01 PR-015): it always combines time (the batch's own age and its
quiet period) with a thermal fact whenever a temperature sensor exists.
Without a sensor only the weakest state is reachable, and the result says
so through an explicit limitation instead of pretending it measured heat.

A continuous bin mixes material of different ages, so the whole-container
claim is capped at the weakest state (docs/07 §10); a tracked batch is the
only candidate for a sharp decision (§11). The forecast is a window with
its own confidence — never a date (§12) — and an estimate for gardening,
not a laboratory analysis (§13).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import ceil, floor

from .constants import (
    MATURITY_CONFIDENCE_2_SIGNALS,
    MATURITY_CONFIDENCE_3_SIGNALS,
    MATURITY_CONFIDENCE_4_PLUS_SIGNALS,
    MATURITY_CONTINUOUS_CONFIDENCE_CAP,
    MATURITY_FORECAST_BASELINE_SPREAD,
    MATURITY_FORECAST_GENERIC_CONFIDENCE,
    MATURITY_FORECAST_GENERIC_SPREAD,
    MATURITY_FORECAST_MIN_SPAN,
    MATURITY_GARDEN_MIN_ELAPSED,
    MATURITY_MIN_ELAPSED,
    MATURITY_MIN_SIGNALS,
    MATURITY_QUIET,
    PHASE_CURE_MAX,
    PHASE_CURE_MIN,
    PHASE_CURE_RANGE,
    PHASE_CURE_WINDOW,
    PHASE_PEAK_RECENT,
    PHASE_PEAK_SIGNIFICANT,
    PHASE_THERMOPHILIC_CURRENT,
    SENSOR_STALE_AFTER,
)
from .cycle import Baseline
from .evidence import Evidence
from .model import BinData, Capability, CompostMethod, MaturityState, Provenance
from .temperature import TemperatureAnalysis, history_points

_SENSOR_SOURCE = "sensor:internal_temperature"
_HISTORY_SOURCE = "user_history"
_SECONDS_PER_DAY = 86400.0


@dataclass(frozen=True, slots=True)
class MaturityForecast:
    """Estimated days until garden use — a window, never a date (docs/07 §12)."""

    min_days: int
    max_days: int
    confidence: int
    limitations: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class MaturityResult:
    """How ready this bin's material is, with its support (docs/07 §3, §9).

    `state is None` means UNKNOWN — there is no "sort of ready" member, and
    the forecast is absent rather than guessed when there is nothing to
    estimate or the bin is not a tracked batch.
    """

    state: MaturityState | None
    provenance: Provenance
    confidence: int
    evidence: tuple[Evidence, ...] = ()
    limitations: tuple[str, ...] = ()
    forecast: MaturityForecast | None = None
    method: CompostMethod | None = None


def assess_maturity(
    data: BinData,
    analysis: TemperatureAnalysis,
    now: datetime,
    baseline: Baseline | None = None,
) -> MaturityResult:
    """Evaluate how ready the material of one bin is at `now`.

    Inputs are only what the bin really has: its own cycles, its own logged
    additions and its own thermal history (docs/11 §2: nothing crosses a
    bin boundary).
    """
    method = data.environment.method
    if not data.material_additions:
        return MaturityResult(
            state=None,
            provenance=Provenance.UNKNOWN,
            confidence=0,
            limitations=("no_material_logged",),
            method=method,
        )

    anchor = _anchor(data)
    elapsed = now - anchor
    elapsed_days = round(elapsed.total_seconds() / _SECONDS_PER_DAY, 1)
    current = _current_temperature(data, now)
    points = history_points(data.temperature_history, now)

    if _has_temperature(data) and current is None:
        # A configured sensor that is not reporting cannot support a claim
        # (docs/06 §13: stale is not current) — and neither can silence.
        return MaturityResult(
            state=None,
            provenance=Provenance.UNKNOWN,
            confidence=0,
            limitations=("no_current_temperature",),
            method=method,
        )

    evidence: list[Evidence] = []
    limitations: list[str] = []
    heat = _heat_evidence(analysis, evidence)
    cooled = current is not None and current < PHASE_THERMOPHILIC_CURRENT
    if current is not None and not cooled:
        # Still thermophilic: whatever the calendar says, it is not ready.
        return MaturityResult(
            state=None,
            provenance=Provenance.UNKNOWN,
            confidence=0,
            limitations=("thermophilic_now",),
            method=method,
        )
    settled = _settled(points, analysis, current, now, evidence)
    aged = elapsed >= MATURITY_MIN_ELAPSED
    quiet, quiet_days = _quiet(data, now)
    if aged:
        evidence.append(
            Evidence(
                source=_HISTORY_SOURCE,
                parameter="batch_age_sufficient",
                value=elapsed_days,
                timestamp=anchor,
                role="supports_maturity",
            )
        )
    if quiet:
        evidence.append(
            Evidence(
                source=_HISTORY_SOURCE,
                parameter="no_recent_additions",
                value=quiet_days,
                timestamp=max(item.timestamp for item in data.material_additions),
                role="supports_maturity",
            )
        )
    garden_age = elapsed >= MATURITY_GARDEN_MIN_ELAPSED
    if garden_age and quiet:
        evidence.append(
            Evidence(
                source=_HISTORY_SOURCE,
                parameter="garden_age_reached",
                value=elapsed_days,
                timestamp=anchor,
                role="supports_maturity",
            )
        )

    state: MaturityState | None = None
    if not aged:
        limitations.append("insufficient_maturity_evidence")
    elif not quiet:
        # A freshly fed batch is not ready — and "not yet" is UNKNOWN,
        # never a maturity state (docs/07 §9).
        limitations.append("recent_material_addition")
    elif len(evidence) < MATURITY_MIN_SIGNALS:
        limitations.append("insufficient_maturity_evidence")
    elif settled and garden_age:
        state = MaturityState.LIKELY_SUITABLE_FOR_GARDEN_USE
    elif settled:
        state = MaturityState.LIKELY_MATURE
    else:
        state = MaturityState.READY_FOR_CURING
        if heat is None and not points:
            limitations.append("no_temperature_evidence")

    if state is None:
        return MaturityResult(
            state=None,
            provenance=Provenance.UNKNOWN,
            confidence=0,
            evidence=tuple(evidence),
            limitations=tuple(limitations),
            method=method,
        )

    confidence = _confidence(len(evidence))
    if method is not CompostMethod.BATCH:
        # Mixed ages in one container: the claim stays the weakest one
        # (docs/07 §10) and the confidence says why (docs/07 §10, §11).
        if state is not MaturityState.READY_FOR_CURING:
            state = MaturityState.READY_FOR_CURING
        confidence = min(confidence, MATURITY_CONTINUOUS_CONFIDENCE_CAP)
        if method is CompostMethod.CONTINUOUS:
            limitations.append("continuous_bin_heterogeneous")
        else:
            limitations.append("compost_method_unknown")

    return MaturityResult(
        state=state,
        provenance=Provenance.INFERRED,
        confidence=confidence,
        evidence=tuple(evidence),
        limitations=tuple(limitations),
        forecast=_forecast(state, elapsed_days, confidence, method, baseline),
        method=method,
    )


def _anchor(data: BinData) -> datetime:
    """When the current batch began — cycles first, first addition last.

    The caller guarantees at least one material addition, so an anchor
    always exists: a batch without a start date cannot have an age.
    """
    tracked = [cycle for cycle in data.cycles if cycle.completed_at is not None]
    active = next(
        (cycle for cycle in data.cycles if cycle.completed_at is None), None
    )
    if active is not None:
        return active.started_at
    if tracked:
        return max(tracked, key=lambda cycle: cycle.started_at).started_at
    return min(item.timestamp for item in data.material_additions)


def _has_temperature(data: BinData) -> bool:
    """True when this bin is supposed to report a temperature at all."""
    return Capability.INTERNAL_TEMPERATURE in data.capabilities


def _current_temperature(data: BinData, now: datetime) -> float | None:
    """The bound, fresh internal temperature — None when unusable (docs/04)."""
    if not _has_temperature(data):
        return None
    reading = data.internal_temperature
    if reading is None or reading.value is None or reading.timestamp is None:
        return None
    if (now - reading.timestamp) > SENSOR_STALE_AFTER:
        return None
    return reading.value


def _heat_evidence(
    analysis: TemperatureAnalysis, evidence: list[Evidence]
) -> float | None:
    """Record the significant peak if the batch really had one (docs/07 §8)."""
    peak = analysis.peak_value
    if peak is None or peak < PHASE_PEAK_SIGNIFICANT:
        return None
    evidence.append(
        Evidence(
            source=_SENSOR_SOURCE,
            parameter="significant_peak_reached",
            value=round(peak, 1),
            timestamp=analysis.peak_timestamp or analysis.latest_timestamp,
            role="supports_maturity",
        )
    )
    return peak


def _settled(
    points: list[tuple[datetime, float]],
    analysis: TemperatureAnalysis,
    current: float | None,
    now: datetime,
    evidence: list[Evidence],
) -> bool:
    """A full cure window of stability with no recent significant peak.

    Stability cannot be claimed for days that were never observed: the
    window must be covered by history (docs/07 §8), and the band is the
    documented cure band — near-ambient is unknown without an ambient
    reference, so it stays an honest absolute range (docs/04).
    """
    if current is None or not points:
        return False
    if (now - points[0][0]) < PHASE_CURE_WINDOW:
        return False
    values = [
        value for timestamp, value in points if (now - timestamp) <= PHASE_CURE_WINDOW
    ]
    if len(values) < 2:
        return False
    if not all(PHASE_CURE_MIN <= value <= PHASE_CURE_MAX for value in values):
        return False
    if not PHASE_CURE_MIN <= current <= PHASE_CURE_MAX:
        return False
    if max(values) - min(values) > PHASE_CURE_RANGE:
        return False
    peak_timestamp = analysis.peak_timestamp
    if peak_timestamp is not None and (now - peak_timestamp) <= PHASE_PEAK_RECENT:
        return False
    evidence.append(
        Evidence(
            source=_SENSOR_SOURCE,
            parameter="settled_window_range",
            value=round(max(values) - min(values), 1),
            timestamp=points[-1][0],
            role="supports_maturity",
        )
    )
    return True


def _quiet(data: BinData, now: datetime) -> tuple[bool, float]:
    """No fresh addition for MATURITY_QUIET — `(met, days_since_last)`."""
    latest = max(item.timestamp for item in data.material_additions)
    days = round((now - latest).total_seconds() / _SECONDS_PER_DAY, 1)
    return (now - latest) >= MATURITY_QUIET, days


def _confidence(signal_count: int) -> int:
    """Confidence grows with corroborating signals, never with repetition."""
    if signal_count >= 4:
        return MATURITY_CONFIDENCE_4_PLUS_SIGNALS
    if signal_count == 3:
        return MATURITY_CONFIDENCE_3_SIGNALS
    return MATURITY_CONFIDENCE_2_SIGNALS


def _forecast(
    state: MaturityState,
    elapsed_days: float,
    claim_confidence: int,
    method: CompostMethod | None,
    baseline: Baseline | None,
) -> MaturityForecast | None:
    """A window in days until garden use — never a date (docs/07 §12).

    Personal when this bin's own baseline is reliable (docs/18 §7), generic
    — and explicitly flagged — when it is not (docs/18 §6: distance and
    missing data degrade confidence).
    """
    if state is MaturityState.LIKELY_SUITABLE_FOR_GARDEN_USE:
        return None  # already there: nothing left to estimate
    if method is not CompostMethod.BATCH:
        return None  # a mixed container has no single window (docs/07 §10)

    personal = baseline is not None
    target = (
        baseline.median_duration_days
        if personal and baseline is not None
        else float(MATURITY_GARDEN_MIN_ELAPSED.days)
    )
    spread = (
        MATURITY_FORECAST_BASELINE_SPREAD
        if personal
        else MATURITY_FORECAST_GENERIC_SPREAD
    )
    remaining = target - elapsed_days
    low = max(ceil(remaining - spread), 0)
    high = max(floor(remaining + spread), low + MATURITY_FORECAST_MIN_SPAN)
    factor = 100 if personal else MATURITY_FORECAST_GENERIC_CONFIDENCE
    forecast_confidence = (claim_confidence * factor + 50) // 100
    return MaturityForecast(
        min_days=low,
        max_days=high,
        confidence=forecast_confidence,
        limitations=(
            ()
            if personal
            else ("forecast_without_personal_baseline",)
        ),
    )
