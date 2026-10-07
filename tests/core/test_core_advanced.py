"""Advanced signal diagnostics (M9, docs/00 §6, docs/14 §7, docs/05).

Expected findings are hand-computed from `core/constants.py`: a reading
never claims anything alone (docs/06 §8), a unit we do not understand
supports nothing (docs/04) and a stale reading is not a reading.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from custom_components.smart_compost.core.advanced import diagnose_signals
from custom_components.smart_compost.core.assessment import assess
from custom_components.smart_compost.core.constants import (
    AMMONIA_ELEVATED,
    DIAGNOSTIC_CONFIDENCE_2_SIGNALS,
    DIAGNOSTIC_CONFIDENCE_3_PLUS_SIGNALS,
    FILL_NEARLY_FULL,
    FILL_UNIT,
    VOC_ELEVATED,
)
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


def _reading(
    value: float, unit: str, minutes_ago: float = 1.0
) -> NumericValue:
    return NumericValue(
        value=value,
        unit=unit,
        provenance=Provenance.MEASURED,
        timestamp=NOW - timedelta(minutes=minutes_ago),
    )


def _material(hours_ago: float, kind: str = "food_scraps") -> MaterialAddition:
    return MaterialAddition(
        timestamp=NOW - timedelta(hours=hours_ago),
        material_type=kind,
        quantity_value=None,
        quantity_unit=None,
        quantity_precision=QuantityPrecision.QUALITATIVE,
    )


def _data(
    *,
    voc: NumericValue | None = None,
    ammonia: NumericValue | None = None,
    fill: NumericValue | None = None,
    moisture: NumericValue | None = None,
    samples: tuple[NumericValue, ...] = (),
    materials: tuple[MaterialAddition, ...] = (),
) -> BinData:
    """BinData whose capabilities mirror the present readings (docs/04)."""
    capabilities = {Capability.MANUAL_DATA}
    if voc is not None or ammonia is not None:
        capabilities.add(Capability.GAS_SIGNALS)
    if fill is not None:
        capabilities.add(Capability.WEIGHT_FILL)
    if moisture is not None:
        capabilities.add(Capability.INTERNAL_MOISTURE)
    if samples:
        capabilities.add(Capability.INTERNAL_TEMPERATURE)
    return BinData(
        capabilities=frozenset(capabilities),
        internal_moisture=moisture,
        voc=voc,
        ammonia=ammonia,
        fill_level=fill,
        temperature_history=samples,
        material_additions=materials,
    )


def _findings(data: BinData):
    return diagnose_signals(data, analyze(data.temperature_history, NOW), NOW)


def _falling_series() -> tuple[NumericValue, ...]:
    """7 samples over 3 h falling 40 → 16 °C (−8 °C/h), newest 6 min old."""
    return tuple(
        _reading(40.0 - 4.0 * index, "°C", minutes_ago=180 - 30 * index + 6)
        for index in range(7)
    )


# --- The two-signal rule -----------------------------------------------------


def test_a_lone_elevated_voc_is_not_a_finding() -> None:
    # Fresh, clearly elevated — and still only ONE signal (docs/06 §8).
    data = _data(voc=_reading(1500.0, "ppb"))
    assert _findings(data) == ()


def test_elevated_voc_with_too_wet_moisture_reports_anaerobic() -> None:
    data = _data(
        voc=_reading(1500.0, "ppb"),
        moisture=_reading(75.0, FILL_UNIT),  # 70–79.9 → too_wet (40)
    )
    findings = _findings(data)
    assert [item.code for item in findings] == ["possible_anaerobic_activity"]
    assert findings[0].confidence == DIAGNOSTIC_CONFIDENCE_2_SIGNALS
    assert findings[0].signals == (
        "elevated_voc",
        "internal_moisture_too_wet",
    )


def test_elevated_voc_with_a_fresh_falling_series_reports_anaerobic() -> None:
    data = _data(voc=_reading(1500.0, "ppb"), samples=_falling_series())
    findings = _findings(data)
    assert [item.code for item in findings] == ["possible_anaerobic_activity"]
    assert findings[0].signals == ("elevated_voc", "temperature_falling")


def test_three_signals_raise_the_confidence() -> None:
    data = _data(
        voc=_reading(1500.0, "ppb"),
        moisture=_reading(75.0, FILL_UNIT),
        samples=_falling_series(),
    )
    findings = _findings(data)
    assert [item.code for item in findings] == ["possible_anaerobic_activity"]
    assert findings[0].confidence == DIAGNOSTIC_CONFIDENCE_3_PLUS_SIGNALS
    assert len(findings[0].signals) == 3


def test_a_stale_series_cannot_speak_about_now() -> None:
    # The trend is falling, but the last sample is 2 h old: history, not a
    # current signal (docs/06 §13).
    stale = tuple(
        NumericValue(
            value=item.value,
            unit=item.unit,
            provenance=item.provenance,
            timestamp=item.timestamp - timedelta(hours=2),
        )
        for item in _falling_series()
    )
    data = _data(voc=_reading(1500.0, "ppb"), samples=stale)
    assert _findings(data) == ()


def test_a_fresh_series_without_the_binding_claims_nothing() -> None:
    # Same fresh series, but the temperature binding is gone: without the
    # capability there is no series to corroborate with (docs/04).
    unbound = BinData(
        capabilities=frozenset(
            {Capability.MANUAL_DATA, Capability.GAS_SIGNALS}
        ),
        voc=_reading(1500.0, "ppb"),
        temperature_history=_falling_series(),
    )
    assert _findings(unbound) == ()


# --- Units and staleness: unknown stays unknown (docs/04) -------------------


def test_a_unit_we_do_not_understand_supports_nothing() -> None:
    # An index, not a concentration: even with wetness as a second signal
    # the VOC reading cannot corroborate anything.
    data = _data(
        voc=_reading(5000.0, "index"),
        moisture=_reading(75.0, FILL_UNIT),
    )
    assert _findings(data) == ()


def test_a_stale_gas_reading_claims_nothing() -> None:
    data = _data(
        voc=_reading(1500.0, "ppb", minutes_ago=45.0),
        moisture=_reading(75.0, FILL_UNIT),
    )
    assert _findings(data) == ()


def test_the_threshold_is_the_boundary_and_is_unit_checked() -> None:
    # 999 ppb < 1000 → not elevated; 1000 ppb == the threshold → elevated.
    below = _data(
        voc=_reading(999.0, "ppb"), moisture=_reading(75.0, FILL_UNIT)
    )
    assert _findings(below) == ()
    at = _data(
        voc=_reading(VOC_ELEVATED["ppb"], "ppb"),
        moisture=_reading(75.0, FILL_UNIT),
    )
    assert [item.code for item in _findings(at)] == [
        "possible_anaerobic_activity"
    ]


def test_the_same_threshold_in_another_supported_unit() -> None:
    # 1.5 ppm ≥ 1.0 and 4500 µg/m³ ≥ 4000: the table decides, not us.
    for value, unit in ((1.5, "ppm"), (4500.0, "µg/m³")):
        data = _data(
            voc=_reading(value, unit), moisture=_reading(75.0, FILL_UNIT)
        )
        assert [item.code for item in _findings(data)] == [
            "possible_anaerobic_activity"
        ], unit


# --- Ammonia + balance -------------------------------------------------------


def test_elevated_ammonia_alone_claims_nothing() -> None:
    assert _findings(_data(ammonia=_reading(5000.0, "ppb"))) == ()


def test_elevated_ammonia_with_a_green_heavy_balance_reports_nitrogen() -> None:
    greens = (
        _material(6.0, "food_scraps"),
        _material(12.0, "grass_clippings"),
        _material(30.0, "coffee_grounds"),
    )
    data = _data(ammonia=_reading(AMMONIA_ELEVATED["ppb"], "ppb"), materials=greens)
    findings = _findings(data)
    assert [item.code for item in findings] == ["possible_nitrogen_excess"]
    assert findings[0].confidence == DIAGNOSTIC_CONFIDENCE_2_SIGNALS
    assert findings[0].signals == ("elevated_ammonia", "greens_without_browns")


def test_elevated_ammonia_with_a_balanced_mix_claims_nothing() -> None:
    # Greens AND browns → the balance domain says "balanced", which is no
    # second signal at all.
    mixed = (
        _material(6.0, "food_scraps"),
        _material(12.0, "grass_clippings"),
        _material(30.0, "dry_leaves"),
    )
    data = _data(ammonia=_reading(6000.0, "ppb"), materials=mixed)
    assert _findings(data) == ()


def test_ammonia_below_the_threshold_is_not_elevated() -> None:
    greens = (
        _material(6.0, "food_scraps"),
        _material(12.0, "grass_clippings"),
        _material(30.0, "coffee_grounds"),
    )
    data = _data(
        ammonia=_reading(AMMONIA_ELEVATED["ppb"] - 1.0, "ppb"), materials=greens
    )
    assert _findings(data) == ()


# --- Fill level --------------------------------------------------------------


def test_a_high_fill_level_alone_claims_nothing() -> None:
    assert _findings(_data(fill=_reading(90.0, FILL_UNIT))) == ()


def test_a_high_fill_level_that_is_still_being_fed_is_reported() -> None:
    data = _data(
        fill=_reading(90.0, FILL_UNIT), materials=(_material(6.0),)
    )
    findings = _findings(data)
    assert [item.code for item in findings] == ["bin_nearly_full"]
    assert findings[0].confidence == DIAGNOSTIC_CONFIDENCE_2_SIGNALS
    assert findings[0].signals == ("fill_level_high", "recent_fueling")


def test_an_old_addition_is_not_recent_fueling() -> None:
    data = _data(fill=_reading(90.0, FILL_UNIT), materials=(_material(48.0),))
    assert _findings(data) == ()


def test_fill_below_the_threshold_is_not_high() -> None:
    data = _data(
        fill=_reading(FILL_NEARLY_FULL - 1.0, FILL_UNIT),
        materials=(_material(6.0),),
    )
    assert _findings(data) == ()


def test_fill_in_a_unit_that_is_not_a_percentage_supports_nothing() -> None:
    data = _data(fill=_reading(100.0, "litre"), materials=(_material(6.0),))
    assert _findings(data) == ()


def test_a_stale_fill_reading_supports_nothing() -> None:
    data = _data(
        fill=_reading(90.0, FILL_UNIT, minutes_ago=45.0),
        materials=(_material(6.0),),
    )
    assert _findings(data) == ()


# --- Threshold tables stay honest (hand-computed from constants) -------------

def test_the_supported_threshold_tables_are_the_documented_ones() -> None:
    assert VOC_ELEVATED == {
        "ppb": 1000.0,
        "ppm": 1.0,
        "µg/m³": 4000.0,
        "ug/m³": 4000.0,
    }
    assert AMMONIA_ELEVATED == {
        "ppb": 5000.0,
        "ppm": 5.0,
        "µg/m³": 3500.0,
        "ug/m³": 3500.0,
    }
    assert FILL_NEARLY_FULL == 85.0
    assert FILL_UNIT == "%"


# --- The findings reach the assessment ---------------------------------------


def test_the_assessment_carries_the_advanced_findings() -> None:
    data = _data(
        voc=_reading(1500.0, "ppb"),
        moisture=_reading(75.0, FILL_UNIT),
        materials=(_material(6.0),),
    )
    assessment = assess(data, NOW)
    assert [item.code for item in assessment.diagnostics] == [
        "possible_anaerobic_activity"
    ]

    # Without the gas reading the same bin yields no such finding.
    quiet = _data(
        moisture=_reading(75.0, FILL_UNIT), materials=(_material(6.0),)
    )
    assert assess(quiet, NOW).diagnostics == ()
