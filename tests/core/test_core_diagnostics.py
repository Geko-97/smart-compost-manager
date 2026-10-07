"""Multi-signal diagnostics (M5): a finding needs corroboration (docs/06).

Expected numbers are hand-computed from `core/constants.py`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from custom_components.smart_compost.core.constants import (
    DIAGNOSTIC_CONFIDENCE_2_SIGNALS,
    DIAGNOSTIC_CONFIDENCE_3_PLUS_SIGNALS,
    THERMAL_FAST_RISE,
)
from custom_components.smart_compost.core.diagnostics import diagnose
from custom_components.smart_compost.core.model import (
    BinData,
    Capability,
    MaterialAddition,
    NumericValue,
    Provenance,
    QuantityPrecision,
)
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
    material_hours_ago: float | None = None,
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
    additions: tuple[MaterialAddition, ...] = ()
    if material_hours_ago is not None:
        additions = (
            MaterialAddition(
                timestamp=NOW - timedelta(hours=material_hours_ago),
                material_type="food_scraps",
                quantity_value=None,
                quantity_unit=None,
                quantity_precision=QuantityPrecision.QUALITATIVE,
            ),
        )
    return BinData(
        capabilities=frozenset(capabilities),
        internal_temperature=temperature,
        temperature_history=samples,
        material_additions=additions,
    )


def _diagnose(data: BinData):
    return diagnose(data, analyze(data.temperature_history, NOW), NOW)


def _rising_series() -> tuple[NumericValue, ...]:
    """7 samples over 2 h rising 30 → 48 °C (9 °C/h, way above the fast
    rise threshold)."""
    return tuple(
        _sample(
            hours_ago=minutes_ago / 60.0,
            value=30.0 + (120 - minutes_ago) * 0.15,
        )
        for minutes_ago in (120, 100, 80, 60, 40, 20, 0)
    )


# --- The corroboration rule --------------------------------------------------


def test_without_a_bound_sensor_there_are_no_findings() -> None:
    data = _data(_rising_series(), 48.0, bound=False)
    assert _diagnose(data) == ()


def test_a_stale_series_cannot_support_a_claim_about_now() -> None:
    # The current reading is fresh, but the series stopped 2 h ago.
    data = _data(
        (_sample(3, 30.0), _sample(2, 31.0)),
        48.0,
        minutes_ago=1.0,
    )
    assert _diagnose(data) == ()


def test_a_single_signal_is_never_a_diagnosis() -> None:
    # Fresh state, but no trend evidence (2 samples): "elevated_now" alone
    # must not produce a finding (docs/06 §8).
    data = _data((_sample(10 / 60, 48.0), _sample(1 / 60, 50.0)), 50.0)
    assert _diagnose(data) == ()


def test_rapid_heating_needs_two_signals() -> None:
    data = _data(_rising_series(), 48.0)
    findings = _diagnose(data)
    assert [item.code for item in findings] == ["rapid_heating"]
    finding = findings[0]
    assert finding.confidence == DIAGNOSTIC_CONFIDENCE_2_SIGNALS
    assert finding.signals == ("fast_rise", "elevated_now")
    # 18 °C over 2 h = 9 °C/h.
    assert THERMAL_FAST_RISE == 1.0


def test_a_recent_addition_corroborates_and_raises_confidence() -> None:
    data = _data(_rising_series(), 48.0, material_hours_ago=6.0)
    findings = _diagnose(data)
    assert [item.code for item in findings] == ["rapid_heating"]
    finding = findings[0]
    assert finding.confidence == DIAGNOSTIC_CONFIDENCE_3_PLUS_SIGNALS
    assert finding.signals == ("fast_rise", "elevated_now", "recent_fueling")

    # An old addition (3 days) is outside the window: no corroboration.
    stale = _data(_rising_series(), 48.0, material_hours_ago=72.0)
    assert _diagnose(stale)[0].confidence == DIAGNOSTIC_CONFIDENCE_2_SIGNALS


def test_rapid_cooling_needs_fall_drop_and_cold_state() -> None:
    # 8 samples over ~24 h (enough for a trend) with a fresh last sample.
    samples = (
        _sample(24, 60.0),
        _sample(12, 50.0),
        _sample(6, 42.0),
        _sample(4, 38.0),
        _sample(3, 36.0),
        _sample(2, 34.0),
        _sample(1, 32.0),
        _sample(0.25, 31.0),
    )
    data = _data(samples, 30.0)
    findings = _diagnose(data)
    assert [item.code for item in findings] == ["rapid_cooling"]
    finding = findings[0]
    assert finding.confidence == DIAGNOSTIC_CONFIDENCE_3_PLUS_SIGNALS
    assert finding.signals == ("falling_fast", "dropped_from_peak", "now_cool")


def test_stagnation_is_flat_cold_and_never_heated() -> None:
    samples = tuple(
        _sample(hours_ago=minutes_ago / 60.0, value=9.0)
        for minutes_ago in (180, 150, 120, 90, 60, 30, 0)
    )
    data = _data(samples, 9.0)
    findings = _diagnose(data)
    assert [item.code for item in findings] == ["stagnation"]
    finding = findings[0]
    assert finding.confidence == DIAGNOSTIC_CONFIDENCE_3_PLUS_SIGNALS
    assert finding.signals == ("stable_trend", "low_now", "no_significant_peak")


def test_stagnation_at_two_signals_is_still_reported_with_less_confidence() -> None:
    # Flat at 20 °C: stable and never heated, but not low → two signals.
    samples = tuple(
        _sample(hours_ago=minutes_ago / 60.0, value=20.0)
        for minutes_ago in (180, 150, 120, 90, 60, 30, 0)
    )
    data = _data(samples, 20.0)
    findings = _diagnose(data)
    assert [item.code for item in findings] == ["stagnation"]
    assert findings[0].confidence == DIAGNOSTIC_CONFIDENCE_2_SIGNALS
    assert findings[0].signals == ("stable_trend", "no_significant_peak")
