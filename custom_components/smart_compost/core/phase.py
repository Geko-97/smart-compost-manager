"""Biological phase inference from the thermal history (M5, docs/07).

Phase is a *trajectory*: it is inferred from the shape of the temperature
series — start, rise, duration, peak, fall, settling — never from the
calendar and never from a single point. Every result carries what
docs/07 §3 requires: phase, provenance, confidence, evidence and
limitations; without enough history the phase stays UNKNOWN, because an
honest "I don't know" beats a plausible story (docs/07 §5).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .constants import (
    DIAGNOSTIC_CONFIDENCE_2_SIGNALS,
    DIAGNOSTIC_CONFIDENCE_3_PLUS_SIGNALS,
    PHASE_COOLING_DROP,
    PHASE_COOLING_MAX_CURRENT,
    PHASE_CURE_MAX,
    PHASE_CURE_MIN,
    PHASE_CURE_MIN_SAMPLES,
    PHASE_CURE_RANGE,
    PHASE_CURE_WINDOW,
    PHASE_MESOPHILIC_MAX,
    PHASE_MESOPHILIC_MIN,
    PHASE_MIN_SAMPLES,
    PHASE_PEAK_RECENT,
    PHASE_PEAK_SIGNIFICANT,
    PHASE_THERMOPHILIC_CURRENT,
    PHASE_THERMOPHILIC_MIN_DWELL,
    SENSOR_STALE_AFTER,
)
from .evidence import Evidence
from .model import BinData, Capability, Phase, Provenance
from .temperature import TemperatureAnalysis, history_points

_PHASE_SOURCE = "sensor:internal_temperature"


@dataclass(frozen=True, slots=True)
class PhaseResult:
    """The phase of one bin with its support (docs/07 §3)."""

    phase: Phase | None
    provenance: Provenance
    confidence: int
    evidence: tuple[Evidence, ...] = ()
    limitations: tuple[str, ...] = ()

    @property
    def signals(self) -> tuple[str, ...]:
        """Machine-readable names of the signals that decided the phase."""
        return tuple(item.parameter for item in self.evidence)


def detect_phase(
    data: BinData, analysis: TemperatureAnalysis, now: datetime
) -> PhaseResult:
    """Infer the biological phase from fresh readings and thermal history.

    A phase claim needs a fresh current temperature (stale data is not
    current, docs/06 §13) and at least PHASE_MIN_SAMPLES history samples;
    on top of that at least two independent signals must agree — the same
    corroboration rule the diagnostics use (docs/06).
    """
    points = history_points(data.temperature_history, now)
    limitations: list[str] = []
    if not points:
        limitations.append("no_temperature_history")
    elif len(points) < PHASE_MIN_SAMPLES:
        limitations.append("insufficient_phase_evidence")

    current = _current_temperature(data, now)
    if current is None:
        limitations.append("no_current_temperature")

    if current is None or len(points) < PHASE_MIN_SAMPLES:
        return PhaseResult(
            phase=None,
            provenance=Provenance.UNKNOWN,
            confidence=0,
            limitations=tuple(limitations),
        )

    latest_timestamp = points[-1][0]
    peak_value = analysis.peak_value
    peak_timestamp = analysis.peak_timestamp

    phase: Phase | None = None
    evidence: list[Evidence] = []

    if _is_curing(points, peak_value, current, now):
        phase = Phase.CURING
        cure_values = [
            value
            for timestamp, value in points
            if (now - timestamp) <= PHASE_CURE_WINDOW
        ]
        evidence = [
            _signal(
                "prior_significant_peak",
                peak_value,
                peak_timestamp or latest_timestamp,
            ),
            _signal(
                "settled_window_range",
                round(max(cure_values) - min(cure_values), 1),
                latest_timestamp,
            ),
            _signal("current_settled", current, latest_timestamp),
        ]
    elif current >= PHASE_THERMOPHILIC_CURRENT:
        phase = Phase.THERMOPHILIC
        evidence = [_signal("current_high", current, latest_timestamp)]
        if analysis.time_above_thermophilic >= PHASE_THERMOPHILIC_MIN_DWELL:
            evidence.append(
                _signal(
                    "sustained_above_threshold",
                    round(
                        analysis.time_above_thermophilic.total_seconds() / 3600.0, 2
                    ),
                    latest_timestamp,
                )
            )
        if peak_value is not None and peak_value >= PHASE_PEAK_SIGNIFICANT:
            evidence.append(
                _signal(
                    "significant_peak",
                    peak_value,
                    peak_timestamp or latest_timestamp,
                )
            )
    elif (
        peak_value is not None
        and peak_timestamp is not None
        and _is_cooling(peak_value, peak_timestamp, current, now)
    ):
        phase = Phase.COOLING
        evidence = [
            _signal("recent_significant_peak", peak_value, peak_timestamp),
            _signal(
                "dropped_from_peak",
                round(peak_value - current, 1),
                latest_timestamp,
            ),
            _signal("now_cool", current, latest_timestamp),
        ]
    elif (
        PHASE_MESOPHILIC_MIN <= current < PHASE_MESOPHILIC_MAX
        and not _recent_peak(peak_value, peak_timestamp, now)
    ):
        phase = Phase.MESOPHILIC
        evidence = [
            _signal("current_in_mesophilic_range", current, latest_timestamp),
            _signal(
                "no_recent_significant_peak",
                peak_value,
                peak_timestamp or latest_timestamp,
            ),
        ]

    if phase is None or len(evidence) < 2:
        # One signal alone is an observation, not a phase (docs/06: a
        # finding needs at least two independent signals).
        limitations.append(
            "insufficient_phase_evidence"
            if evidence or _branch_matched(points, peak_value, current, now)
            else "outside_phase_ranges"
        )
        return PhaseResult(
            phase=None,
            provenance=Provenance.UNKNOWN,
            confidence=0,
            limitations=tuple(limitations),
        )

    return PhaseResult(
        phase=phase,
        provenance=Provenance.INFERRED,
        confidence=_confidence(len(evidence)),
        evidence=tuple(evidence),
        limitations=tuple(limitations),
    )


def _branch_matched(
    points: list[tuple[datetime, float]],
    peak_value: float | None,
    current: float,
    now: datetime,
) -> bool:
    """Whether the current state at least matched some phase branch.

    Distinguishes "the signals disagreed" (insufficient) from "the state
    is outside every phase range" (e.g. a near-freezing bin).
    """
    if current >= PHASE_THERMOPHILIC_CURRENT:
        return True
    if _is_curing(points, peak_value, current, now):
        return True
    if PHASE_MESOPHILIC_MIN <= current < PHASE_MESOPHILIC_MAX:
        return True
    return False


def _current_temperature(data: BinData, now: datetime) -> float | None:
    """The bound, fresh internal temperature — None when unusable (docs/04)."""
    reading = data.internal_temperature
    if Capability.INTERNAL_TEMPERATURE not in data.capabilities:
        return None
    if reading is None or reading.value is None or reading.timestamp is None:
        return None
    if (now - reading.timestamp) > SENSOR_STALE_AFTER:
        return None
    return reading.value


def _signal(
    name: str,
    value: str | float | int | None,
    timestamp: datetime,
) -> Evidence:
    return Evidence(
        source=_PHASE_SOURCE,
        parameter=name,
        value=value,
        timestamp=timestamp,
        role="supports_phase",
    )


def _confidence(signal_count: int) -> int:
    """Confidence grows with corroborating signals, never with repetition."""
    if signal_count >= 3:
        return DIAGNOSTIC_CONFIDENCE_3_PLUS_SIGNALS
    return DIAGNOSTIC_CONFIDENCE_2_SIGNALS


def _is_curing(
    points: list[tuple[datetime, float]],
    peak_value: float | None,
    current: float,
    now: datetime,
) -> bool:
    """Curing: a significant past peak, then a long stable settle (docs/07 §8).

    The whole cure window must be covered by history — stability cannot be
    claimed for days that were never observed.
    """
    if (now - points[0][0]) < PHASE_CURE_WINDOW:
        return False
    cure_values = [
        value for timestamp, value in points if (now - timestamp) <= PHASE_CURE_WINDOW
    ]
    if len(cure_values) < PHASE_CURE_MIN_SAMPLES:
        return False
    if not all(PHASE_CURE_MIN <= value <= PHASE_CURE_MAX for value in cure_values):
        return False
    if max(cure_values) - min(cure_values) > PHASE_CURE_RANGE:
        return False
    return (
        peak_value is not None
        and peak_value >= PHASE_PEAK_SIGNIFICANT
        and PHASE_MESOPHILIC_MIN <= current <= PHASE_CURE_MAX
    )


def _is_cooling(
    peak_value: float, peak_timestamp: datetime, current: float, now: datetime
) -> bool:
    """Cooling: a persistent drop after recent significant activity
    (docs/07 §7 — not a single dip)."""
    if peak_value < PHASE_PEAK_SIGNIFICANT:
        return False
    if (now - peak_timestamp) > PHASE_PEAK_RECENT:
        return False
    if current > peak_value - PHASE_COOLING_DROP:
        return False
    return current <= PHASE_COOLING_MAX_CURRENT


def _recent_peak(
    peak_value: float | None, peak_timestamp: datetime | None, now: datetime
) -> bool:
    """True when a significant peak happened recently (mid-trajectory)."""
    if peak_value is None or peak_timestamp is None:
        return False
    return (
        peak_value >= PHASE_PEAK_SIGNIFICANT
        and (now - peak_timestamp) <= PHASE_PEAK_RECENT
    )
