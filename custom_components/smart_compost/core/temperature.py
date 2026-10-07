"""Temperature time series: recording and analysis (M5, docs/10).

Temperature of a compost bin is a *series*, not a point (docs/10). This
module owns two things:

* ``record_sample`` — appending measurements to a bounded history
  (rate-limited, windowed, capped — memory stays flat from 1 to 10+ bins);
* ``analyze`` — every time-series fact the engine may quote: trend, peak,
  extremes, time above thresholds.

Honest by construction: a trend is claimed only when TREND_MIN_SAMPLES and
TREND_MIN_SPAN are met; otherwise it is UNKNOWN — never a slope guessed
from two noisy points (docs/06: insufficient evidence → UNKNOWN).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from .constants import (
    MAX_TEMPERATURE_SAMPLES,
    SAMPLE_MIN_INTERVAL,
    SAMPLE_SIGNIFICANT_DELTA,
    SLOPE_STABLE_DEADBAND,
    TEMPERATURE_HISTORY_WINDOW,
    TIME_ABOVE_HOT,
    TIME_ABOVE_THERMOPHILIC,
    TREND_MIN_SAMPLES,
    TREND_MIN_SPAN,
)
from .model import NumericValue


class TrendDirection(StrEnum):
    """Direction of the temperature trend — UNKNOWN without enough evidence."""

    RISING = "rising"
    STABLE = "stable"
    FALLING = "falling"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class TemperatureAnalysis:
    """Time-series facts about one bin's temperature history.

    Every field is None (or UNKNOWN) when the history cannot support it:
    the absence of evidence is never rendered as a number (docs/04).
    """

    sample_count: int = 0
    span: timedelta = timedelta(0)
    trend: TrendDirection = TrendDirection.UNKNOWN
    slope_per_hour: float | None = None
    latest_value: float | None = None
    latest_timestamp: datetime | None = None
    min_value: float | None = None
    max_value: float | None = None
    peak_value: float | None = None
    peak_timestamp: datetime | None = None
    time_above_thermophilic: timedelta = timedelta(0)
    time_above_hot: timedelta = timedelta(0)

    @property
    def has_history(self) -> bool:
        """True when at least one usable sample exists in the window."""
        return self.sample_count > 0

    @property
    def supports_trend(self) -> bool:
        """True only when TREND_MIN_SAMPLES and TREND_MIN_SPAN are met."""
        return self.slope_per_hour is not None


def record_sample(
    history: tuple[NumericValue, ...], reading: NumericValue
) -> tuple[NumericValue, ...]:
    """Append one measurement, rate-limited, windowed and capped.

    Returns the SAME tuple when nothing qualifies, so callers can detect
    whether anything changed. Invalid input (missing value, no timestamp,
    non-finite number) is refused and never becomes history (docs/04).
    """
    if reading.value is None or reading.timestamp is None:
        return history
    if not math.isfinite(reading.value):
        return history
    if reading.timestamp.utcoffset() is None:
        raise ValueError("sample timestamps must be timezone-aware")

    last = history[-1] if history else None
    if last is not None and last.timestamp is not None and last.value is not None:
        elapsed = reading.timestamp - last.timestamp
        moved = abs(reading.value - last.value)
        if elapsed <= timedelta(0) or (
            elapsed < SAMPLE_MIN_INTERVAL and moved < SAMPLE_SIGNIFICANT_DELTA
        ):
            # Out-of-order, duplicate or a negligible wobble: history keeps
            # its order and stays bounded (docs/10: not every raw sample).
            return history

    cutoff = reading.timestamp - TEMPERATURE_HISTORY_WINDOW
    trimmed = tuple(
        item
        for item in history
        if item.timestamp is not None and item.timestamp >= cutoff
    )
    updated = (*trimmed, reading)
    if len(updated) > MAX_TEMPERATURE_SAMPLES:
        updated = updated[-MAX_TEMPERATURE_SAMPLES:]
    return updated


def history_points(
    history: tuple[NumericValue, ...], now: datetime
) -> list[tuple[datetime, float]]:
    """Usable (timestamp, value) pairs inside the history window, oldest first.

    Samples older than TEMPERATURE_HISTORY_WINDOW or dated in the future
    (clock skew) are not current history and are excluded.
    """
    points: list[tuple[datetime, float]] = []
    for item in history:
        if item.value is None or item.timestamp is None:
            continue
        age = now - item.timestamp
        if timedelta(0) <= age <= TEMPERATURE_HISTORY_WINDOW:
            points.append((item.timestamp, item.value))
    points.sort(key=lambda pair: pair[0])
    return points


def analyze(
    history: tuple[NumericValue, ...], now: datetime
) -> TemperatureAnalysis:
    """Compute every time-series fact from one bin's history at `now`."""
    points = history_points(history, now)
    if not points:
        return TemperatureAnalysis()

    values = [value for _, value in points]
    span = points[-1][0] - points[0][0]
    slope, trend = _trend(points, span)
    peak_value = max(values)
    peak_timestamp = points[values.index(peak_value)][0]

    return TemperatureAnalysis(
        sample_count=len(points),
        span=span,
        trend=trend,
        slope_per_hour=slope,
        latest_value=values[-1],
        latest_timestamp=points[-1][0],
        min_value=min(values),
        max_value=max(values),
        peak_value=peak_value,
        peak_timestamp=peak_timestamp,
        time_above_thermophilic=_time_above(points, TIME_ABOVE_THERMOPHILIC),
        time_above_hot=_time_above(points, TIME_ABOVE_HOT),
    )


def _trend(
    points: list[tuple[datetime, float]], span: timedelta
) -> tuple[float | None, TrendDirection]:
    """Least-squares slope in °C/h — None unless the evidence is enough."""
    if len(points) < TREND_MIN_SAMPLES or span < TREND_MIN_SPAN:
        return None, TrendDirection.UNKNOWN
    slope = _least_squares_slope(points)
    if slope is None:
        return None, TrendDirection.UNKNOWN
    if slope > SLOPE_STABLE_DEADBAND:
        return slope, TrendDirection.RISING
    if slope < -SLOPE_STABLE_DEADBAND:
        return slope, TrendDirection.FALLING
    return slope, TrendDirection.STABLE


def _least_squares_slope(
    points: list[tuple[datetime, float]],
) -> float | None:
    """Slope in °C per hour (ordinary least squares over the sample points)."""
    origin = points[0][0]
    xs = [(timestamp - origin).total_seconds() / 3600.0 for timestamp, _ in points]
    ys = [value for _, value in points]
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    denominator = sum((x - mean_x) ** 2 for x in xs)
    if denominator == 0.0:
        return None
    numerator = sum(
        (x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True)
    )
    return numerator / denominator


def _time_above(
    points: list[tuple[datetime, float]], threshold: float
) -> timedelta:
    """Time the series spent above `threshold`, interpolating crossings.

    Only measured intervals count: the dwell time after the last sample is
    unknown, so it is never added (docs/04: no extrapolation).
    """
    seconds = 0.0
    for (t0, v0), (t1, v1) in zip(points, points[1:], strict=False):
        duration = (t1 - t0).total_seconds()
        if duration <= 0.0:
            continue
        if v0 >= threshold and v1 >= threshold:
            seconds += duration
        elif v0 >= threshold > v1:
            seconds += duration * (v0 - threshold) / (v0 - v1)
        elif v1 >= threshold > v0:
            seconds += duration * (v1 - threshold) / (v1 - v0)
    return timedelta(seconds=seconds)
