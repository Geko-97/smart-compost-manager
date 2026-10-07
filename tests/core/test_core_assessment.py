"""Assessment engine invariants: never invent, keep the triade distinct.

Expected numbers are hand-computed from `core/constants.py` so any silent
weight change fails the suite (docs/24_CODING_RULES.md).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from custom_components.smart_compost.core.assessment import BinData, assess
from custom_components.smart_compost.core.model import (
    ActionCode,
    CycleStage,
    MaterialAddition,
    ObservationCategory,
    Provenance,
    QuantityPrecision,
    UserObservation,
)

NOW = datetime(2026, 10, 6, 12, 0, 0, tzinfo=UTC)


def _material(days_ago: float) -> MaterialAddition:
    return MaterialAddition(
        timestamp=NOW - timedelta(days=days_ago),
        material_type="food_scraps",
        quantity_value=2.0,
        quantity_unit="bucket",
        quantity_precision=QuantityPrecision.APPROXIMATE,
    )


def _observation(days_ago: float) -> UserObservation:
    return UserObservation(
        timestamp=NOW - timedelta(days=days_ago),
        category=ObservationCategory.MOISTURE,
        value="damp",
    )


def test_empty_bin_never_invents_anything() -> None:
    assessment = assess(BinData(), NOW)

    # Health is UNKNOWN (None), not 0 — a claim would be a lie (docs/06).
    assert assessment.health.score is None
    assert assessment.health.provenance is Provenance.UNKNOWN
    # Zero inputs honestly read as zero data quality.
    assert assessment.data_quality == 0
    # Confidence: 100 * 0.5 * (1 evidence / 3) = 16.67 → 17.
    assert assessment.confidence == 17

    assert assessment.cycle_stage is CycleStage.NEW
    assert assessment.action.code is ActionCode.LOG_FIRST_ADDITION
    assert assessment.action.reason_code == "no_materials_logged"


def test_no_evidence_pretends_to_be_a_measurement() -> None:
    for data in (BinData(), BinData(material_additions=(_material(1.0),))):
        assessment = assess(data, NOW)
        assert assessment.evidence
        assert all(
            item.source == "user_history" for item in assessment.evidence
        )
        assert assessment.health.provenance is Provenance.UNKNOWN


def test_manual_data_raises_data_quality_without_faking_health() -> None:
    data = BinData(
        material_additions=(_material(1.0),),
        observations=(_observation(1.0),),
    )
    assessment = assess(data, NOW)

    # DQ: 100 * (0.3 * (0.5 material + 0.3 observation) + 0.2 * fresh) = 44.
    assert assessment.data_quality == 44
    assert assessment.confidence == 17  # still one piece of evidence
    assert assessment.health.score is None  # manual data ≠ measurable health

    assert assessment.cycle_stage is CycleStage.ACTIVE
    assert assessment.action.code is ActionCode.NONE
    assert assessment.action.reason_code == "no_issues_detected"


def test_triade_stays_three_different_numbers() -> None:
    data = BinData(
        material_additions=(_material(1.0),),
        observations=(_observation(1.0),),
    )
    assessment = assess(data, NOW)
    health = assessment.health.score
    values = {health, assessment.data_quality, assessment.confidence}
    assert None in values
    assert assessment.data_quality != assessment.confidence
    assert len(values) == 3


def test_observation_alone_does_not_start_a_cycle() -> None:
    assessment = assess(BinData(observations=(_observation(1.0),)), NOW)
    # DQ: 100 * (0.3 * 0.3 + 0.2 * fresh) = 29.
    assert assessment.data_quality == 29
    assert assessment.cycle_stage is CycleStage.NEW
    assert assessment.action.code is ActionCode.LOG_FIRST_ADDITION


def test_stale_data_decays_confidence_and_data_quality() -> None:
    assessment = assess(BinData(material_additions=(_material(60.0),)), NOW)
    # DQ: 100 * (0.3 * 0.5 + 0.2 * 0.0) = 15, freshness fully decayed.
    assert assessment.data_quality == 15
    # Evidence older than STALE_WINDOW contributes no support → 0.
    assert assessment.confidence == 0
    # Yet the conclusion itself does not flip: stage is still ACTIVE.
    assert assessment.cycle_stage is CycleStage.ACTIVE


def test_ageing_data_is_half_fresh() -> None:
    assessment = assess(BinData(material_additions=(_material(10.0),)), NOW)
    # DQ: 100 * (0.3 * 0.5 + 0.2 * 0.5) = 25.
    assert assessment.data_quality == 25
    # Confidence: 100 * 0.5 * (1/3 * 0.5) = 8.33 → 8.
    assert assessment.confidence == 8


def test_limitations_declare_what_is_missing() -> None:
    assessment = assess(BinData(), NOW)
    assert "no_evaluable_domains" in assessment.limitations
    assert "no_internal_temperature" in assessment.limitations
    assert "no_internal_moisture" in assessment.limitations


def test_naive_clock_is_rejected() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        assess(BinData(), datetime(2026, 10, 6, 12, 0, 0))


def test_assessment_is_pure_and_deterministic() -> None:
    bin_a = BinData(material_additions=(_material(1.0),))
    bin_b = BinData()

    first = assess(bin_a, NOW)
    assess(bin_b, NOW)  # assessing another bin must not leak anything
    second = assess(bin_a, NOW)

    assert first == second
    assert assess(bin_b, NOW) != first
    assert assess(bin_b, NOW).cycle_stage is CycleStage.NEW
