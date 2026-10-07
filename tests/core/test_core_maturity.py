"""Maturity, readiness and forecast (M8, docs/07 §8–§13, docs/18).

Expected outcomes are hand-computed from `core/constants.py`: a claim needs
MATURITY_MIN_SIGNALS independent signals, a continuous bin is capped at the
weakest state, and the forecast is a window (never a date) that degrades
without a personal baseline.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from custom_components.smart_compost.core.assessment import assess
from custom_components.smart_compost.core.constants import (
    MATURITY_CONTINUOUS_CONFIDENCE_CAP,
    MATURITY_GARDEN_MIN_ELAPSED,
    MATURITY_MIN_ELAPSED,
    MATURITY_QUIET,
)
from custom_components.smart_compost.core.cycle import Baseline
from custom_components.smart_compost.core.maturity import (
    MaturityResult,
    assess_maturity,
)
from custom_components.smart_compost.core.model import (
    BinData,
    Capability,
    CompostMethod,
    EnvironmentProfile,
    MaterialAddition,
    MaturityState,
    NumericValue,
    Provenance,
    QuantityPrecision,
)
from custom_components.smart_compost.core.temperature import analyze

NOW = datetime(2026, 10, 6, 12, 0, 0, tzinfo=UTC)


def _material(days_ago: float) -> MaterialAddition:
    return MaterialAddition(
        timestamp=NOW - timedelta(days=days_ago),
        material_type="food_scraps",
        quantity_value=None,
        quantity_unit=None,
        quantity_precision=QuantityPrecision.QUALITATIVE,
    )


def _reading(value: float, days_ago: float) -> NumericValue:
    return NumericValue(
        value=value,
        unit="°C",
        provenance=Provenance.MEASURED,
        timestamp=NOW - timedelta(days=days_ago),
    )


def _bin(
    method: CompostMethod | None = CompostMethod.BATCH,
    materials: tuple[MaterialAddition, ...] = (),
    samples: tuple[NumericValue, ...] = (),
    current: NumericValue | None = None,
) -> BinData:
    capabilities = {Capability.MANUAL_DATA}
    if samples or current is not None:
        capabilities.add(Capability.INTERNAL_TEMPERATURE)
    return BinData(
        environment=EnvironmentProfile(method=method),
        capabilities=frozenset(capabilities),
        internal_temperature=current,
        temperature_history=samples,
        material_additions=materials,
    )


def _maturity(data: BinData, baseline: Baseline | None = None) -> MaturityResult:
    return assess_maturity(data, analyze(data.temperature_history, NOW), NOW, baseline)


def _settled_history() -> tuple[NumericValue, ...]:
    """A significant peak 6 days ago, then a stable cure window (docs/07 §8)."""
    return (
        _reading(60.0, 6.0),
        _reading(28.0, 5.0),
        _reading(27.0, 4.0),
        _reading(26.0, 3.0),
        _reading(26.0, 2.0),
        _reading(25.0, 1.0),
    )


def _fresh(value: float) -> NumericValue:
    return NumericValue(
        value=value,
        unit="°C",
        provenance=Provenance.MEASURED,
        timestamp=NOW - timedelta(minutes=1),
    )


# --- Nothing to declare ------------------------------------------------------


def test_without_material_there_is_no_maturity_at_all() -> None:
    result = _maturity(_bin())

    assert result.state is None
    assert result.provenance is Provenance.UNKNOWN
    assert result.confidence == 0
    assert result.limitations == ("no_material_logged",)
    assert result.forecast is None


def test_a_young_batch_is_unknown_not_immature() -> None:
    data = _bin(materials=(_material(3.0),))

    result = _maturity(data)

    # MATURITY_MIN_ELAPSED has not passed: "not yet" is UNKNOWN (docs/07 §9).
    assert result.state is None
    assert result.confidence == 0
    assert result.limitations == ("insufficient_maturity_evidence",)
    assert MATURITY_MIN_ELAPSED.days == 7


def test_a_recently_fed_batch_is_unknown_until_it_is_quiet() -> None:
    data = _bin(materials=(_material(20.0), _material(1.0)))

    result = _maturity(data)

    # The anchor is the FIRST addition (20 days: aged), but the fresh
    # feeding 1 day ago means nothing may be claimed about readiness.
    assert result.state is None
    assert result.limitations == ("recent_material_addition",)
    assert MATURITY_QUIET.days == 7


# --- The zero-sensor path ----------------------------------------------------


def test_without_a_sensor_only_reaching_curing_is_honest() -> None:
    data = _bin(materials=(_material(10.0),))

    result = _maturity(data)

    # Two independent signals — batch age and silence — get the WEAKEST
    # state; heat was never observed, and the result says so (docs/07 §5).
    assert result.state is MaturityState.READY_FOR_CURING
    assert result.provenance is Provenance.INFERRED
    assert result.confidence == 55
    assert result.limitations == ("no_temperature_evidence",)
    assert [item.parameter for item in result.evidence] == [
        "batch_age_sufficient",
        "no_recent_additions",
    ]


def test_a_stale_sensor_cannot_support_any_claim() -> None:
    stale = NumericValue(
        value=25.0,
        unit="°C",
        provenance=Provenance.MEASURED,
        timestamp=NOW - timedelta(hours=2),
    )
    data = _bin(
        materials=(_material(30.0),),
        samples=_settled_history(),
        current=stale,
    )

    result = _maturity(data)

    # The sensor exists but stopped reporting: stale is not current
    # (docs/06 §13), so the bin falls back to UNKNOWN, not to a guess.
    assert result.state is None
    assert result.confidence == 0
    assert result.limitations == ("no_current_temperature",)


def test_a_still_thermophilic_batch_is_not_ready_for_anything() -> None:
    data = _bin(
        materials=(_material(30.0),),
        samples=_settled_history(),
        current=_fresh(52.0),
    )

    result = _maturity(data)

    assert result.state is None
    assert result.limitations == ("thermophilic_now",)


# --- The thermal ladder ------------------------------------------------------


def test_settled_history_reaches_the_strongest_readiness() -> None:
    data = _bin(
        materials=(_material(30.0),),
        samples=_settled_history(),
        current=_fresh(25.0),
    )

    result = _maturity(data)

    # Five corroborating signals: peak, stable window, age, silence and
    # the garden window (30 ≥ 21 days) — never a single variable.
    assert result.state is MaturityState.LIKELY_SUITABLE_FOR_GARDEN_USE
    assert result.confidence == 85
    assert result.limitations == ()
    assert [item.parameter for item in result.evidence] == [
        "significant_peak_reached",
        "settled_window_range",
        "batch_age_sufficient",
        "no_recent_additions",
        "garden_age_reached",
    ]
    # Already usable: there is nothing left to estimate (docs/07 §12).
    assert result.forecast is None
    assert MATURITY_GARDEN_MIN_ELAPSED.days == 21


def test_settled_but_young_batch_is_likely_mature_with_a_window() -> None:
    data = _bin(
        materials=(_material(10.0),),
        samples=_settled_history(),
        current=_fresh(25.0),
    )

    result = _maturity(data)

    # Four signals (age 10 < 21 days: no garden claim yet).
    assert result.state is MaturityState.LIKELY_MATURE
    assert result.confidence == 85

    forecast = result.forecast
    assert forecast is not None
    # Generic window: 21 − 10 = 11 days to the target, ± 8 spread.
    assert forecast.min_days == 3
    assert forecast.max_days == 19
    # (85 * 70 + 50) // 100 = 60 — a generic window is less certain.
    assert forecast.confidence == 60
    assert forecast.limitations == ("forecast_without_personal_baseline",)


def test_a_personal_baseline_narrows_the_window() -> None:
    data = _bin(
        materials=(_material(10.0),),
        samples=_settled_history(),
        current=_fresh(25.0),
    )
    baseline = Baseline(
        completed_cycles=3,
        confidence=60,
        median_duration_days=12.0,
        median_peak=60.0,
    )

    forecast = _maturity(data, baseline).forecast

    assert forecast is not None
    # This bin usually finishes in 12 days; 10 are gone: 12 − 10 = 2,
    # ± 4 spread → 0–6 days (never a negative or a single date).
    assert forecast.min_days == 0
    assert forecast.max_days == 6
    # (85 * 100 + 50) // 100 = 85 — the window comes from real history.
    assert forecast.confidence == 85
    assert forecast.limitations == ()


def test_heat_without_stability_only_reaches_curing() -> None:
    data = _bin(
        materials=(_material(10.0),),
        # A peak and one warm reading: no stable cure window (docs/07 §8).
        samples=(_reading(60.0, 6.0), _reading(35.0, 1.0)),
        current=_fresh(35.0),
    )

    result = _maturity(data)

    # Three signals: peak, age, silence — settled is NOT one of them.
    assert result.state is MaturityState.READY_FOR_CURING
    assert result.confidence == 70
    assert result.limitations == ()
    assert result.forecast is not None
    assert result.forecast.limitations == ("forecast_without_personal_baseline",)
    # (70 * 70 + 50) // 100 = 49.
    assert result.forecast.confidence == 49


# --- Continuous vs batch (docs/07 §10, §11) ---------------------------------


def test_a_continuous_bin_never_gets_a_batch_sharp_decision() -> None:
    data = _bin(
        method=CompostMethod.CONTINUOUS,
        materials=(_material(10.0),),
        samples=_settled_history(),
        current=_fresh(25.0),
    )

    result = _maturity(data)

    # The same evidence that says LIKELY_MATURE for a batch is capped to
    # the weakest state: the container mixes material of different ages.
    assert result.state is MaturityState.READY_FOR_CURING
    assert result.confidence == MATURITY_CONTINUOUS_CONFIDENCE_CAP
    assert result.limitations == ("continuous_bin_heterogeneous",)
    # No single window exists for a mixed container.
    assert result.forecast is None


def test_an_unconfigured_method_is_not_assumed_to_be_a_batch() -> None:
    data = _bin(
        method=None,
        materials=(_material(10.0),),
        samples=_settled_history(),
        current=_fresh(25.0),
    )

    result = _maturity(data)

    # "Not told" must never be read as "batch" (docs/04).
    assert result.state is MaturityState.READY_FOR_CURING
    assert result.confidence == MATURITY_CONTINUOUS_CONFIDENCE_CAP
    assert result.limitations == ("compost_method_unknown",)
    assert result.forecast is None
    assert result.method is None


# --- Assessment integration --------------------------------------------------


def test_the_assessment_carries_the_maturity_result() -> None:
    data = _bin(
        materials=(_material(30.0),),
        samples=_settled_history(),
        current=_fresh(25.0),
    )

    assessment = assess(data, NOW)

    assert assessment.maturity.state is (
        MaturityState.LIKELY_SUITABLE_FOR_GARDEN_USE
    )
    assert assessment.maturity.method is CompostMethod.BATCH
    # Maturity is a separate question from the phase: both are reported.
    assert assessment.phase.phase is not None
    assert assessment.maturity.confidence == 85
