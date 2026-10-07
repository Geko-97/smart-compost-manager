"""Phase inference (M5): a trajectory needs history and corroboration (docs/07).

Expected outcomes are hand-computed from `core/constants.py`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from custom_components.smart_compost.core.constants import (
    DIAGNOSTIC_CONFIDENCE_2_SIGNALS,
    DIAGNOSTIC_CONFIDENCE_3_PLUS_SIGNALS,
)
from custom_components.smart_compost.core.model import (
    BinData,
    Capability,
    NumericValue,
    Phase,
    Provenance,
)
from custom_components.smart_compost.core.phase import detect_phase
from custom_components.smart_compost.core.temperature import analyze

NOW = datetime(2026, 10, 6, 12, 0, 0, tzinfo=UTC)


def _sample(hours_ago: float, value: float) -> NumericValue:
    return NumericValue(
        value=value,
        unit="°C",
        provenance=Provenance.MEASURED,
        timestamp=NOW - timedelta(hours=hours_ago),
    )


def _data(
    samples: tuple[NumericValue, ...],
    current_value: float | None,
    *,
    bound: bool = True,
    minutes_ago: float = 1.0,
) -> BinData:
    capabilities = {Capability.MANUAL_DATA}
    temperature: NumericValue | None = None
    if bound:
        capabilities.add(Capability.INTERNAL_TEMPERATURE)
        if current_value is not None:
            temperature = NumericValue(
                value=current_value,
                unit="°C",
                provenance=Provenance.MEASURED,
                timestamp=NOW - timedelta(minutes=minutes_ago),
            )
    return BinData(
        capabilities=frozenset(capabilities),
        internal_temperature=temperature,
        temperature_history=samples,
    )


def _phase(data: BinData):
    return detect_phase(data, analyze(data.temperature_history, NOW), NOW)


def _flat_series(hours: float, value: float, count: int) -> tuple[NumericValue, ...]:
    step = hours / (count - 1)
    return tuple(
        _sample(hours_ago=hours - index * step, value=value)
        for index in range(count)
    )


# --- Insufficient evidence stays UNKNOWN -------------------------------------


def test_no_history_never_claims_a_phase() -> None:
    result = _phase(_data((), 25.0))
    assert result.phase is None
    assert result.provenance is Provenance.UNKNOWN
    assert result.confidence == 0
    assert result.signals == ()
    assert result.limitations == ("no_temperature_history",)


def test_unbound_sensor_supports_no_phase() -> None:
    result = _phase(_data((), None, bound=False))
    assert result.phase is None
    assert result.limitations == (
        "no_temperature_history",
        "no_current_temperature",
    )


def test_a_single_sample_is_not_a_trajectory() -> None:
    result = _phase(_data((_sample(0.1, 25.0),), 25.0))
    assert result.phase is None
    assert result.limitations == ("insufficient_phase_evidence",)


def test_stale_current_reading_blocks_the_phase() -> None:
    # Fresh-looking history, but the current reading is 40 minutes old.
    data = _data(_flat_series(hours=6, value=55.0, count=8), 55.0, minutes_ago=40.0)
    result = _phase(data)
    assert result.phase is None
    assert result.provenance is Provenance.UNKNOWN
    assert result.limitations == ("no_current_temperature",)


# --- Thermophilic ------------------------------------------------------------


def test_thermophilic_needs_duration_not_a_spike() -> None:
    # 4 h of history, all above the threshold: duration + level + peak.
    data = _data(_flat_series(hours=4.0, value=55.0, count=9), 55.0)
    result = _phase(data)
    assert result.phase is Phase.THERMOPHILIC
    assert result.provenance is Provenance.INFERRED
    assert result.confidence == DIAGNOSTIC_CONFIDENCE_3_PLUS_SIGNALS
    assert result.signals == (
        "current_high",
        "sustained_above_threshold",
        "significant_peak",
    )


def test_one_hot_reading_is_not_a_phase() -> None:
    # Just crossed 40 °C: one signal (current_high) and no corroborating
    # duration or peak — the honest answer is UNKNOWN.
    data = _data((_sample(2, 39.0), _sample(1, 41.0)), 41.0)
    result = _phase(data)
    assert result.phase is None
    assert result.confidence == 0
    assert result.limitations == ("insufficient_phase_evidence",)


# --- Cooling -----------------------------------------------------------------


def test_cooling_is_a_persistent_drop_after_a_recent_peak() -> None:
    data = _data(
        (_sample(24, 60.0), _sample(12, 50.0), _sample(6, 40.0), _sample(2, 32.0)),
        30.0,
    )
    result = _phase(data)
    assert result.phase is Phase.COOLING
    assert result.confidence == DIAGNOSTIC_CONFIDENCE_3_PLUS_SIGNALS
    assert result.signals == (
        "recent_significant_peak",
        "dropped_from_peak",
        "now_cool",
    )


def test_a_peak_outside_the_recent_window_is_no_longer_cooling() -> None:
    # Peak 6 days ago (> PHASE_PEAK_RECENT), stable low since then:
    # not cooling, and the settle window makes it curing.
    samples = (
        _sample(24 * 6, 55.0),
        _sample(24 * 4, 22.0),
        _sample(24 * 3, 23.0),
        _sample(24 * 2, 21.0),
        _sample(24, 22.0),
        _sample(6, 21.0),
        _sample(1, 22.0),
    )
    result = _phase(_data(samples, 22.0))
    assert result.phase is Phase.CURING


# --- Curing ------------------------------------------------------------------


def test_curing_needs_a_past_peak_and_a_stable_settle_window() -> None:
    samples = (
        _sample(24 * 6, 55.0),  # the significant past peak
        _sample(24 * 4, 21.0),
        _sample(24 * 3, 23.0),
        _sample(24 * 2, 22.0),
        _sample(24, 21.0),
        _sample(6, 22.0),
        _sample(1, 21.0),
    )
    result = _phase(_data(samples, 22.0))
    assert result.phase is Phase.CURING
    assert result.confidence == DIAGNOSTIC_CONFIDENCE_3_PLUS_SIGNALS
    assert result.signals == (
        "prior_significant_peak",
        "settled_window_range",
        "current_settled",
    )


def test_stability_without_a_prior_peak_is_just_mesophilic() -> None:
    # Same stable settle, but the bin never heated: not "curing".
    samples = (
        _sample(24 * 6, 30.0),
        _sample(24 * 3, 29.0),
        _sample(24, 30.0),
        _sample(6, 29.0),
        _sample(1, 30.0),
    )
    result = _phase(_data(samples, 30.0))
    assert result.phase is Phase.MESOPHILIC


def test_history_shorter_than_the_cure_window_cannot_claim_curing() -> None:
    # Perfectly stable, but only 2 days observed of a 5-day window.
    samples = (
        _sample(48, 22.0),
        _sample(36, 23.0),
        _sample(12, 22.0),
        _sample(1, 22.0),
    )
    result = _phase(_data(samples, 22.0))
    assert result.phase is Phase.MESOPHILIC


# --- Mesophilic and honest fallbacks -----------------------------------------


def test_mesophilic_from_a_calm_current_state() -> None:
    data = _data((_sample(6, 24.0), _sample(3, 26.0)), 25.0)
    result = _phase(data)
    assert result.phase is Phase.MESOPHILIC
    assert result.confidence == DIAGNOSTIC_CONFIDENCE_2_SIGNALS
    assert result.signals == (
        "current_in_mesophilic_range",
        "no_recent_significant_peak",
    )


def test_a_recent_peak_blocks_the_mesophilic_claim() -> None:
    # 36 °C with a significant peak 10 h ago: mid-trajectory, honestly
    # neither thermophilic, nor cooling, nor mesophilic.
    data = _data(
        (_sample(10, 50.0), _sample(4, 42.0), _sample(1, 37.0)),
        36.0,
    )
    result = _phase(data)
    assert result.phase is None
    assert result.limitations == ("insufficient_phase_evidence",)


def test_a_near_freezing_bin_is_outside_every_phase_range() -> None:
    data = _data((_sample(2, 8.0), _sample(1, 9.0)), 9.0)
    result = _phase(data)
    assert result.phase is None
    assert result.limitations == ("outside_phase_ranges",)


def test_phase_detection_is_pure_and_deterministic() -> None:
    data = _data((_sample(6, 24.0), _sample(3, 26.0)), 25.0)
    assert _phase(data) == _phase(data)
    other = _data((), None, bound=False)
    assert _phase(data) != _phase(other)
