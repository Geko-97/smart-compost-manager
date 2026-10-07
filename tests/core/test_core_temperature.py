"""Temperature time series (M5): bounded recording, honest analysis (docs/10).

Expected numbers are hand-computed from `core/constants.py`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from custom_components.smart_compost.core.constants import (
    MAX_TEMPERATURE_SAMPLES,
    SLOPE_STABLE_DEADBAND,
    TREND_MIN_SAMPLES,
    TREND_MIN_SPAN,
)
from custom_components.smart_compost.core.model import NumericValue, Provenance
from custom_components.smart_compost.core.temperature import (
    TrendDirection,
    analyze,
    history_points,
    record_sample,
)

NOW = datetime(2026, 10, 6, 12, 0, 0, tzinfo=UTC)


def _reading(
    value: float, minutes_ago: float = 0.0, unit: str | None = "°C"
) -> NumericValue:
    return NumericValue(
        value=value,
        unit=unit,
        provenance=Provenance.MEASURED,
        timestamp=NOW - timedelta(minutes=minutes_ago),
    )


def _series(points: list[tuple[float, float]]) -> tuple[NumericValue, ...]:
    """Build a history from (minutes_ago, value) pairs, oldest first."""
    return tuple(
        _reading(value, minutes_ago=minutes_ago)
        for minutes_ago, value in sorted(points, reverse=True)
    )


# --- Recording ---------------------------------------------------------------


def test_quiet_wobble_is_rate_limited_but_a_jump_is_kept() -> None:
    history = record_sample((), _reading(50.0, minutes_ago=10))
    assert len(history) == 1

    # 3 minutes < SAMPLE_MIN_INTERVAL and 0.5 °C < SAMPLE_SIGNIFICANT_DELTA.
    unchanged = record_sample(history, _reading(50.5, minutes_ago=7))
    assert unchanged is history

    # A 3 °C jump inside the interval is real movement: always worth keeping.
    jumped = record_sample(history, _reading(53.0, minutes_ago=7))
    assert len(jumped) == 2

    # 2 minutes after the jump, 0.2 °C: still a wobble.
    assert record_sample(jumped, _reading(52.8, minutes_ago=5)) is jumped

    # 7 minutes ≥ SAMPLE_MIN_INTERVAL: recorded regardless of the delta.
    later = record_sample(jumped, _reading(52.5, minutes_ago=0))
    assert len(later) == 3
    assert later[-1].value == 52.5


def test_out_of_order_and_invalid_samples_never_enter_history() -> None:
    history = record_sample((), _reading(50.0, minutes_ago=10))

    # Older than the newest sample: history is never reordered.
    assert record_sample(history, _reading(55.0, minutes_ago=15)) is history
    # Duplicate timestamp: nothing new to remember.
    assert record_sample(history, _reading(55.0, minutes_ago=10)) is history

    # Non-finite and missing values are refused, not stored as 0 (docs/04).
    for bad in (float("nan"), float("inf"), float("-inf")):
        assert len(record_sample((), _reading(bad))) == 0
    assert record_sample((), NumericValue.unknown()) == ()

    naive = NumericValue(
        value=20.0, unit="°C", provenance=Provenance.MEASURED,
        timestamp=datetime(2026, 10, 6, 12, 0, 0),
    )
    with pytest.raises(ValueError, match="timezone-aware"):
        record_sample((), naive)


def test_history_is_capped_at_the_maximum_sample_count() -> None:
    history: tuple[NumericValue, ...] = ()
    for index in range(1100, 0, -1):
        history = record_sample(history, _reading(20.0, minutes_ago=index * 5.0))

    assert len(history) == MAX_TEMPERATURE_SAMPLES
    # The cap drops the OLDEST samples, never the recent ones.
    assert history[-1].timestamp == NOW - timedelta(minutes=5)
    assert history[0].timestamp == NOW - timedelta(minutes=5000)


def test_samples_older_than_the_window_fall_out() -> None:
    history = record_sample((), _reading(90.0, minutes_ago=15 * 24 * 60))
    assert len(history) == 1

    history = record_sample(history, _reading(25.0, minutes_ago=10))
    assert len(history) == 1
    assert history[0].value == 25.0


# --- Analysis ----------------------------------------------------------------


def test_empty_history_is_honestly_unknown() -> None:
    analysis = analyze((), NOW)
    assert analysis.sample_count == 0
    assert analysis.trend is TrendDirection.UNKNOWN
    assert analysis.slope_per_hour is None
    assert not analysis.has_history
    assert not analysis.supports_trend
    assert analysis.peak_value is None
    assert analysis.min_value is None
    assert analysis.time_above_thermophilic == timedelta(0)


def test_future_dated_samples_are_not_history() -> None:
    future = NumericValue(
        value=30.0,
        unit="°C",
        provenance=Provenance.MEASURED,
        timestamp=NOW + timedelta(minutes=5),
    )
    assert history_points((future,), NOW) == []
    assert analyze((future,), NOW).sample_count == 0


def test_trend_needs_both_count_and_span() -> None:
    # One sample short of TREND_MIN_SAMPLES.
    few = _series([(120, 30.0), (90, 33.0), (60, 36.0), (30, 39.0), (0, 42.0)])
    assert len(few) == TREND_MIN_SAMPLES - 1
    analysis = analyze(few, NOW)
    assert analysis.trend is TrendDirection.UNKNOWN
    assert analysis.slope_per_hour is None

    # Enough samples, but the span is shorter than TREND_MIN_SPAN.
    compressed = _series(
        [(50, 30.0), (40, 32.0), (30, 34.0), (20, 36.0), (10, 38.0), (0, 40.0)]
    )
    analysis = analyze(compressed, NOW)
    assert len(compressed) == TREND_MIN_SAMPLES
    assert analysis.span < TREND_MIN_SPAN
    assert analysis.trend is TrendDirection.UNKNOWN
    assert analysis.slope_per_hour is None


def test_trend_directions_and_slope() -> None:
    points = [(120, 30.0), (100, 33.0), (80, 36.0), (60, 39.0), (40, 42.0), (0, 48.0)]
    rising = analyze(_series(points), NOW)
    assert rising.trend is TrendDirection.RISING
    # 18 °C over 2 h, perfectly linear.
    assert rising.slope_per_hour == pytest.approx(9.0)
    assert rising.supports_trend

    falling = analyze(_series([(ago, 78.0 - value) for ago, value in points]), NOW)
    assert falling.trend is TrendDirection.FALLING
    assert falling.slope_per_hour == pytest.approx(-9.0)

    flat = analyze(_series([(ago, 45.0) for ago, _ in points]), NOW)
    assert flat.trend is TrendDirection.STABLE
    assert flat.slope_per_hour == pytest.approx(0.0)


def test_slope_inside_the_deadband_counts_as_stable() -> None:
    assert SLOPE_STABLE_DEADBAND == 0.3
    # +0.25 °C/h over one hour: real but inside the deadband (docs/10 noise).
    points = [
        (60, 30.0),
        (48, 30.05),
        (36, 30.1),
        (24, 30.15),
        (12, 30.2),
        (0, 30.25),
    ]
    analysis = analyze(_series(points), NOW)
    assert analysis.slope_per_hour == pytest.approx(0.25)
    assert analysis.trend is TrendDirection.STABLE


def test_peak_extremes_and_time_above_thresholds() -> None:
    # Interpolated crossing: 30→50 over 30 min crosses 40 °C halfway.
    points = [(90, 30.0), (60, 50.0), (30, 45.0), (0, 45.0)]
    analysis = analyze(_series(points), NOW)
    assert analysis.peak_value == 50.0
    assert analysis.peak_timestamp == NOW - timedelta(minutes=60)
    assert analysis.min_value == 30.0
    assert analysis.max_value == 50.0
    assert analysis.latest_value == 45.0
    # 15 min (crossing) + 30 + 30 = 75 min above 40 °C, none above 70 °C.
    assert analysis.time_above_thermophilic == timedelta(minutes=75)
    assert analysis.time_above_hot == timedelta(0)


def test_time_above_hot_interpolates_both_directions() -> None:
    points = [(60, 60.0), (30, 80.0), (0, 70.0)]
    analysis = analyze(_series(points), NOW)
    # 60→80 crosses 70 halfway (15 min), then 80→70 stays above (30 min).
    assert analysis.time_above_hot == timedelta(minutes=45)


def test_old_samples_are_excluded_from_analysis() -> None:
    history = (
        _reading(90.0, minutes_ago=20 * 24 * 60),
        _reading(20.0, minutes_ago=30),
    )
    analysis = analyze(history, NOW)
    assert analysis.sample_count == 1
    assert analysis.peak_value == 20.0  # the 20-day-old spike is not "recent"
    assert analysis.latest_value == 20.0
