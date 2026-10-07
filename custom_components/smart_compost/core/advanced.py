"""Advanced signal diagnostics (M9, docs/00 §6, docs/14 §7, docs/05).

Roadmap phase 9 adds an input only when it is genuinely useful: every
supported signal carries a DEFINED diagnostic role, and a reading never
claims anything alone — the same two-signal corroboration the rest of the
engine uses (docs/06 §8). Units we do not understand support nothing: an
index or an unknown scale is not a concentration, and guessing it would be
exactly the false precision docs/01 §4 forbids.

Deliberately absent, because no robust role exists yet: CO2 (respiration
is already covered by the temperature series), weight (needs a persisted
trend across a cycle, not one reading), pH and EC (no thresholds we could
stand behind). They stay unbound rather than faked (docs/25 roadmap rule).
"""

from __future__ import annotations

from datetime import datetime

from .constants import (
    AMMONIA_ELEVATED,
    DIAGNOSTIC_CONFIDENCE_2_SIGNALS,
    DIAGNOSTIC_CONFIDENCE_3_PLUS_SIGNALS,
    DIAGNOSTIC_RECENT_FUELING,
    FILL_NEARLY_FULL,
    FILL_UNIT,
    SENSOR_STALE_AFTER,
    VOC_ELEVATED,
)
from .diagnostics import Diagnostic
from .evidence import Evidence
from .health import evaluate_balance, evaluate_moisture
from .model import BinData, Capability, NumericValue
from .temperature import TemperatureAnalysis, TrendDirection


def diagnose_signals(
    data: BinData, analysis: TemperatureAnalysis, now: datetime
) -> tuple[Diagnostic, ...]:
    """The findings the advanced signals can corroborate (M9).

    Returns an empty tuple when nothing reaches two independent signals —
    a lone high VOC reading is an observation, never a diagnosis.
    """
    findings: list[Diagnostic] = []
    for finding in (
        _possible_anaerobic(data, analysis, now),
        _possible_nitrogen_excess(data, now),
        _bin_nearly_full(data, now),
    ):
        if finding is not None:
            findings.append(finding)
    return tuple(findings)


def _possible_anaerobic(
    data: BinData, analysis: TemperatureAnalysis, now: datetime
) -> Diagnostic | None:
    """Elevated VOC + wetness or a falling temperature (docs/05).

    The gas reading alone never proves a microbiological condition
    (docs/01 §4): the second signal decides whether it means anything.
    """
    elevated = _elevated(data.voc, VOC_ELEVATED, now)
    if elevated is None:
        return None
    value, timestamp = elevated
    signals = [_signal("sensor:voc", "elevated_voc", value, timestamp)]

    moisture = evaluate_moisture(data, now)
    reading = data.internal_moisture
    if moisture.reason_code == "too_wet" and reading is not None:
        signals.append(
            _signal(
                "sensor:internal_moisture",
                "internal_moisture_too_wet",
                reading.value if reading.value is not None else "wet",
                reading.timestamp or now,
            )
        )
    if Capability.INTERNAL_TEMPERATURE in data.capabilities:
        falling = _fresh_falling_trend(analysis, now)
        latest = analysis.latest_timestamp
        if falling is not None and latest is not None:
            signals.append(
                _signal(
                    "sensor:internal_temperature",
                    "temperature_falling",
                    falling.value,
                    latest,
                )
            )
    if len(signals) < 2:
        return None
    return Diagnostic(
        code="possible_anaerobic_activity",
        confidence=_confidence(len(signals)),
        evidence=tuple(signals),
    )


def _possible_nitrogen_excess(
    data: BinData, now: datetime
) -> Diagnostic | None:
    """Elevated ammonia + a green-heavy balance: nitrogen escaping (M9)."""
    elevated = _elevated(data.ammonia, AMMONIA_ELEVATED, now)
    if elevated is None:
        return None
    value, timestamp = elevated
    signals = [_signal("sensor:ammonia", "elevated_ammonia", value, timestamp)]

    balance = evaluate_balance(data, now)
    if balance.reason_code == "greens_without_browns":
        signals.append(
            _signal(
                "user_history",
                "greens_without_browns",
                balance.reason_code,
                now,
            )
        )
    if len(signals) < 2:
        return None
    return Diagnostic(
        code="possible_nitrogen_excess",
        confidence=_confidence(len(signals)),
        evidence=tuple(signals),
    )


def _bin_nearly_full(data: BinData, now: datetime) -> Diagnostic | None:
    """A nearly full bin that is still being fed: empty or turn it (M9)."""
    high = _fill_high(data.fill_level, now)
    if high is None:
        return None
    value, timestamp = high
    signals = [_signal("sensor:fill_level", "fill_level_high", value, timestamp)]

    recent = [
        addition
        for addition in data.material_additions
        if (now - addition.timestamp) <= DIAGNOSTIC_RECENT_FUELING
    ]
    if recent:
        signals.append(
            _signal(
                "user_history",
                "recent_fueling",
                len(recent),
                max(item.timestamp for item in recent),
            )
        )
    if len(signals) < 2:
        return None
    return Diagnostic(
        code="bin_nearly_full",
        confidence=_confidence(len(signals)),
        evidence=tuple(signals),
    )


def _fresh_falling_trend(
    analysis: TemperatureAnalysis, now: datetime
) -> TrendDirection | None:
    """A falling series that is still talking about NOW (docs/06 §13).

    A series that stopped hours ago is history, not a current signal: the
    binding must exist and the newest sample must be as fresh as any other
    measurement this module is willing to claim from.
    """
    if analysis.trend is not TrendDirection.FALLING:
        return None
    latest = analysis.latest_timestamp
    if latest is None or (now - latest) > SENSOR_STALE_AFTER:
        return None
    return analysis.trend


def _elevated(
    reading: NumericValue | None,
    thresholds: dict[str, float],
    now: datetime,
) -> tuple[float, datetime] | None:
    """A fresh reading above its unit's threshold — else nothing (docs/04)."""
    if reading is None or reading.value is None or reading.timestamp is None:
        return None
    if (now - reading.timestamp) > SENSOR_STALE_AFTER:
        return None
    unit = (reading.unit or "").strip().lower()
    threshold = thresholds.get(unit)
    if threshold is None or reading.value < threshold:
        return None
    return reading.value, reading.timestamp


def _fill_high(
    reading: NumericValue | None, now: datetime
) -> tuple[float, datetime] | None:
    """A fresh percentage at or above FILL_NEARLY_FULL (unit-checked)."""
    if reading is None or reading.value is None or reading.timestamp is None:
        return None
    if (now - reading.timestamp) > SENSOR_STALE_AFTER:
        return None
    if (reading.unit or "").strip() != FILL_UNIT:
        return None
    if reading.value < FILL_NEARLY_FULL:
        return None
    return reading.value, reading.timestamp


def _signal(
    source: str, parameter: str, value: str | float | int, timestamp: datetime
) -> Evidence:
    return Evidence(
        source=source,
        parameter=parameter,
        value=value,
        timestamp=timestamp,
        role="supports_diagnosis",
    )


def _confidence(signal_count: int) -> int:
    """Confidence grows with corroborating signals, never with repetition."""
    if signal_count >= 3:
        return DIAGNOSTIC_CONFIDENCE_3_PLUS_SIGNALS
    return DIAGNOSTIC_CONFIDENCE_2_SIGNALS
