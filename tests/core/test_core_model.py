"""Core model invariants: provenance cannot lie (docs/04)."""

from __future__ import annotations

import pytest

from custom_components.smart_compost.core.model import (
    EnvironmentProfile,
    Location,
    NumericValue,
    Provenance,
    RainExposure,
    Shelter,
    SunExposure,
    enum_or_unknown,
)


def test_measured_value_requires_timestamp() -> None:
    with pytest.raises(ValueError, match="timestamp"):
        NumericValue(value=20.0, unit="°C", provenance=Provenance.MEASURED)


def test_missing_value_must_be_unknown_never_zero() -> None:
    with pytest.raises(ValueError, match="UNKNOWN"):
        NumericValue(value=None, unit="%", provenance=Provenance.ESTIMATED)


def test_unknown_cannot_carry_a_number() -> None:
    with pytest.raises(ValueError, match="UNKNOWN"):
        NumericValue(value=5.0, unit=None, provenance=Provenance.UNKNOWN)


def test_unknown_constructor_is_the_honest_default() -> None:
    value = NumericValue.unknown(unit="%")
    assert value.value is None
    assert value.provenance is Provenance.UNKNOWN


def test_estimated_value_is_allowed_without_timestamp() -> None:
    value = NumericValue(value=12.5, unit="L", provenance=Provenance.ESTIMATED)
    assert value.value == 12.5


def test_environment_defaults_are_unknown_not_guessed() -> None:
    profile = EnvironmentProfile()
    assert profile.location is Location.UNKNOWN
    assert profile.shelter is Shelter.UNKNOWN
    assert profile.rain_exposure is RainExposure.UNKNOWN
    assert profile.sun_exposure is SunExposure.UNKNOWN


def test_enum_or_unknown_keeps_valid_values() -> None:
    assert enum_or_unknown(Location, "indoor") is Location.INDOOR
    assert enum_or_unknown(Location, Location.INDOOR) is Location.INDOOR


def test_enum_or_unknown_never_invents_a_value() -> None:
    assert enum_or_unknown(Location, "attic??") is Location.UNKNOWN
    assert enum_or_unknown(Location, None) is Location.UNKNOWN
    assert enum_or_unknown(Location, 42) is Location.UNKNOWN
    assert enum_or_unknown(Shelter, "") is Shelter.UNKNOWN
