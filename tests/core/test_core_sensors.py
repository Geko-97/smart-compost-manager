"""Sensor-fed health domains (M4): measured in, UNKNOWN out when unusable.

Expected numbers are hand-computed from `core/constants.py`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from custom_components.smart_compost.core.assessment import BinData, assess
from custom_components.smart_compost.core.model import (
    ActionCode,
    Capability,
    NumericValue,
    ObservationCategory,
    Provenance,
    UserObservation,
)

NOW = datetime(2026, 10, 6, 12, 0, 0, tzinfo=UTC)


def _measurement(
    value: float, minutes_ago: float = 0.0, unit: str = "°C"
) -> NumericValue:
    return NumericValue(
        value=value,
        unit=unit,
        provenance=Provenance.MEASURED,
        timestamp=NOW - timedelta(minutes=minutes_ago),
    )


def _temperature(value: float, minutes_ago: float = 0.0) -> BinData:
    return BinData(
        capabilities=frozenset(
            {Capability.MANUAL_DATA, Capability.INTERNAL_TEMPERATURE}
        ),
        internal_temperature=_measurement(value, minutes_ago),
    )


def _moisture(value: float, minutes_ago: float = 0.0) -> BinData:
    return BinData(
        capabilities=frozenset(
            {Capability.MANUAL_DATA, Capability.INTERNAL_MOISTURE}
        ),
        internal_moisture=_measurement(value, minutes_ago, unit="%"),
    )


def test_thermal_bands() -> None:
    expected = {50.0: 90, 30.0: 80, 10.0: 50, 80.0: 45, 70.0: 70, 4.0: 35}
    for point, score in expected.items():
        assessment = assess(_temperature(point), NOW)
        assert assessment.health.score == score, point
        assert assessment.health.evaluable_domains == ("thermal",)
        assert assessment.health.provenance is Provenance.INFERRED


def test_thermal_bands_are_half_open() -> None:
    # 65 °C is the exclusive upper bound of "thermophilic" → "hot".
    assessment = assess(_temperature(65.0), NOW)
    assert assessment.health.score == 70


def test_thermal_evidence_is_labelled_as_measured_source() -> None:
    assessment = assess(_temperature(50.0), NOW)
    thermal = next(r for r in assessment.health.domains if r.name == "thermal")
    assert thermal.evidence[0].source == "sensor:internal_temperature"
    assert thermal.evidence[0].value == 50.0
    assert thermal.evidence[0].timestamp is not None
    # One reading is the current state, never a trend (docs/10).
    assert "no_temperature_trend" in assessment.health.limitations


def test_moisture_bands() -> None:
    expected = {50.0: 90, 55.0: 90, 35.0: 70, 65.0: 70, 25.0: 40, 75.0: 40, 85.0: 25}
    for point, score in expected.items():
        assessment = assess(_moisture(point), NOW)
        assert assessment.health.score == score, point
        assert assessment.health.evaluable_domains == ("moisture",)


def test_stale_measurement_is_treated_as_unknown() -> None:
    # 35 minutes old > SENSOR_STALE_AFTER (30): the domain must drop even
    # though a value and a capability are present — stale ≠ current.
    assessment = assess(_temperature(50.0, minutes_ago=35.0), NOW)
    assert assessment.health.score is None
    assert assessment.health.provenance is Provenance.UNKNOWN


def test_non_finite_measurement_is_treated_as_unknown() -> None:
    for bad in (float("nan"), float("inf"), float("-inf")):
        assessment = assess(_temperature(bad), NOW)
        assert assessment.health.score is None, bad


def test_capability_and_value_must_agree() -> None:
    # Value without capability: the capability is the switch the HA layer
    # controls, so no domain may light up.
    value_only = BinData(internal_temperature=_measurement(50.0))
    assert assess(value_only, NOW).health.score is None

    # Capability without value: no fabrication either.
    capability_only = BinData(
        capabilities=frozenset({Capability.INTERNAL_TEMPERATURE})
    )
    assert assess(capability_only, NOW).health.score is None


def test_both_sensors_aggregate_with_data_quality_and_confidence() -> None:
    data = BinData(
        capabilities=frozenset(
            {
                Capability.MANUAL_DATA,
                Capability.INTERNAL_TEMPERATURE,
                Capability.INTERNAL_MOISTURE,
            }
        ),
        internal_temperature=_measurement(50.0),
        internal_moisture=_measurement(50.0, unit="%"),
    )
    assessment = assess(data, NOW)

    # mean(thermal 90, moisture 90) = 90.
    assert assessment.health.score == 90
    assert assessment.health.evaluable_domains == ("thermal", "moisture")
    # DQ: 100 * (0.5 * 2/2 measurement coverage) = 50.
    assert assessment.data_quality == 50
    # Confidence: 100 * (0.5 * 2/6 + 0.5 * 3/3) = 66.67 → 67.
    assert assessment.confidence == 67
    # Stage evidence plus both sensor evidences — no fake sources.
    assert {item.source for item in assessment.evidence} == {
        "user_history",
        "sensor:internal_temperature",
        "sensor:internal_moisture",
    }


def test_dry_bin_recommends_watering_first() -> None:
    data = BinData(
        capabilities=frozenset(
            {Capability.MANUAL_DATA, Capability.INTERNAL_MOISTURE}
        ),
        internal_moisture=_measurement(25.0, unit="%"),
        observations=(
            UserObservation(
                timestamp=NOW,
                category=ObservationCategory.ODOR,
                value="sour smell",
            ),
        ),
    )
    assessment = assess(data, NOW)

    # too_dry outranks the aeration observation (measured problem first).
    assert assessment.action.code is ActionCode.WATER_COMPOST
    assert assessment.action.reason_code == "too_dry"
    assert assessment.action.evidence[0].source == "sensor:internal_moisture"
    # And the aeration domain still reports independently.
    aeration = next(
        r for r in assessment.health.domains if r.name == "aeration"
    )
    assert aeration.score == 45


def test_wet_bin_recommends_browns_even_before_any_logging() -> None:
    assessment = assess(_moisture(75.0), NOW)
    assert assessment.action.code is ActionCode.ADD_BROWNS
    assert assessment.action.reason_code == "too_wet"


def test_comfortable_sensor_reading_with_nothing_logged_still_prompts() -> None:
    assessment = assess(_temperature(50.0), NOW)
    assert assessment.action.code is ActionCode.LOG_FIRST_ADDITION
