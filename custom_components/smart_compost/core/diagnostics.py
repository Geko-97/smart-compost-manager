"""Multi-signal diagnostics (M5, docs/06).

A diagnosis is a *finding*, and a finding needs corroboration: at least two
independent signals must agree before anything is claimed, and confidence
grows with the number of distinct signals — never with repetition of the
same one (docs/06 §5 and §8: prefer "possible ..." over claims of
certainty; docs/06 §9: every finding can explain itself through its
evidence).

Diagnostics are claims about NOW, so they are suppressed outright when the
temperature binding or the series itself is stale (docs/06 §13).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .constants import (
    DIAGNOSTIC_CONFIDENCE_2_SIGNALS,
    DIAGNOSTIC_CONFIDENCE_3_PLUS_SIGNALS,
    DIAGNOSTIC_RECENT_FUELING,
    PHASE_COOLING_DROP,
    PHASE_COOLING_MAX_CURRENT,
    PHASE_MESOPHILIC_MIN,
    PHASE_PEAK_RECENT,
    PHASE_PEAK_SIGNIFICANT,
    PHASE_THERMOPHILIC_CURRENT,
    SENSOR_STALE_AFTER,
    THERMAL_FAST_RISE,
)
from .evidence import Evidence
from .model import BinData, Capability
from .temperature import TemperatureAnalysis, TrendDirection

_DIAGNOSTIC_SOURCE = "sensor:internal_temperature"


@dataclass(frozen=True, slots=True)
class Diagnostic:
    """One multi-signal finding: code, confidence, and why it was found."""

    code: str
    confidence: int
    evidence: tuple[Evidence, ...]

    @property
    def signals(self) -> tuple[str, ...]:
        """The independent signals that corroborate this finding."""
        return tuple(item.parameter for item in self.evidence)


def diagnose(
    data: BinData, analysis: TemperatureAnalysis, now: datetime
) -> tuple[Diagnostic, ...]:
    """Every diagnostic finding the available signals can corroborate.

    Returns an empty tuple — never a single-signal guess — when the
    evidence does not reach two independent signals.
    """
    current = _fresh_current(data, analysis, now)
    if current is None:
        return ()

    latest_timestamp = analysis.latest_timestamp
    if latest_timestamp is None:
        return ()
    peak_value = analysis.peak_value
    peak_timestamp = analysis.peak_timestamp
    slope = analysis.slope_per_hour

    candidates: list[tuple[str, list[Evidence]]] = []

    # --- rapid_heating: rising fast while already hot (docs/06) ------------
    heating: list[Evidence] = []
    if slope is not None and slope >= THERMAL_FAST_RISE:
        heating.append(_signal("fast_rise", round(slope, 2), latest_timestamp))
    if current >= PHASE_THERMOPHILIC_CURRENT:
        heating.append(_signal("elevated_now", current, now))
    recent_additions = [
        addition
        for addition in data.material_additions
        if (now - addition.timestamp) <= DIAGNOSTIC_RECENT_FUELING
    ]
    if recent_additions:
        heating.append(
            _signal(
                "recent_fueling",
                len(recent_additions),
                max(item.timestamp for item in recent_additions),
            )
        )
    candidates.append(("rapid_heating", heating))

    # --- rapid_cooling: falling fast after a recent peak (docs/06) ---------
    cooling: list[Evidence] = []
    if slope is not None and slope <= -THERMAL_FAST_RISE:
        cooling.append(_signal("falling_fast", round(slope, 2), latest_timestamp))
    if (
        peak_value is not None
        and peak_timestamp is not None
        and peak_value >= PHASE_PEAK_SIGNIFICANT
        and (now - peak_timestamp) <= PHASE_PEAK_RECENT
        and current <= peak_value - PHASE_COOLING_DROP
    ):
        cooling.append(
            _signal(
                "dropped_from_peak",
                round(peak_value - current, 1),
                latest_timestamp,
            )
        )
    if current <= PHASE_COOLING_MAX_CURRENT:
        cooling.append(_signal("now_cool", current, now))
    candidates.append(("rapid_cooling", cooling))

    # --- stagnation: flat, cold, never heated (docs/06) --------------------
    stagnation: list[Evidence] = []
    if analysis.trend is TrendDirection.STABLE and slope is not None:
        stagnation.append(_signal("stable_trend", round(slope, 2), latest_timestamp))
    if current < PHASE_MESOPHILIC_MIN:
        stagnation.append(_signal("low_now", current, now))
    if peak_value is not None and peak_value < PHASE_PEAK_SIGNIFICANT:
        stagnation.append(
            _signal("no_significant_peak", round(peak_value, 1), peak_timestamp)
        )
    candidates.append(("stagnation", stagnation))

    findings: list[Diagnostic] = []
    for code, signals in candidates:
        if len(signals) < 2:
            # A single signal is an observation, not a diagnosis (docs/06).
            continue
        findings.append(
            Diagnostic(
                code=code,
                confidence=_confidence(len(signals)),
                evidence=tuple(signals),
            )
        )
    return tuple(findings)


def _fresh_current(
    data: BinData, analysis: TemperatureAnalysis, now: datetime
) -> float | None:
    """Fresh current temperature AND a fresh series — else no claim (docs/06)."""
    reading = data.internal_temperature
    if Capability.INTERNAL_TEMPERATURE not in data.capabilities:
        return None
    if reading is None or reading.value is None or reading.timestamp is None:
        return None
    if (now - reading.timestamp) > SENSOR_STALE_AFTER:
        return None
    if analysis.latest_timestamp is None:
        return None
    if (now - analysis.latest_timestamp) > SENSOR_STALE_AFTER:
        return None
    return reading.value


def _signal(name: str, value: str | float | int, timestamp: datetime) -> Evidence:
    return Evidence(
        source=_DIAGNOSTIC_SOURCE,
        parameter=name,
        value=value,
        timestamp=timestamp,
        role="supports_diagnosis",
    )


def _confidence(signal_count: int) -> int:
    """Confidence grows with corroboration, never with repetition."""
    if signal_count >= 3:
        return DIAGNOSTIC_CONFIDENCE_3_PLUS_SIGNALS
    return DIAGNOSTIC_CONFIDENCE_2_SIGNALS
