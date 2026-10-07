"""Health engine invariants (M3): domains must never guess (docs/06, docs/08).

Expected numbers are hand-computed from `core/constants.py`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from custom_components.smart_compost.core.assessment import BinData, assess
from custom_components.smart_compost.core.materials import (
    MaterialCategory,
    classify_material,
    known_material_examples,
)
from custom_components.smart_compost.core.model import (
    ActionCode,
    Intervention,
    InterventionType,
    MaterialAddition,
    ObservationCategory,
    Provenance,
    QuantityPrecision,
    UserObservation,
)

NOW = datetime(2026, 10, 6, 12, 0, 0, tzinfo=UTC)


def _material(kind: str, days_ago: float = 0.0) -> MaterialAddition:
    return MaterialAddition(
        timestamp=NOW - timedelta(days=days_ago),
        material_type=kind,
        quantity_value=None,
        quantity_unit=None,
        quantity_precision=QuantityPrecision.QUALITATIVE,
    )


def _observation(
    value: str,
    days_ago: float = 0.0,
    category: ObservationCategory = ObservationCategory.ODOR,
) -> UserObservation:
    return UserObservation(
        timestamp=NOW - timedelta(days=days_ago),
        category=category,
        value=value,
    )


# --- Knowledge base ----------------------------------------------------------


def test_known_materials_are_classified() -> None:
    assert classify_material("food_scraps") is MaterialCategory.GREEN
    assert classify_material("DRY  Leaves") is MaterialCategory.BROWN
    assert classify_material("cardboard") is MaterialCategory.STRUCTURAL
    assert classify_material("egg shells") is MaterialCategory.NEUTRAL
    for example in known_material_examples():
        assert classify_material(example) is not MaterialCategory.UNKNOWN


def test_unknown_materials_are_never_guessed() -> None:
    assert classify_material("mystery goo") is MaterialCategory.UNKNOWN
    assert classify_material("") is MaterialCategory.UNKNOWN
    assert classify_material("worm castings") is MaterialCategory.UNKNOWN


# --- Balance domain ----------------------------------------------------------


def test_all_green_balance_scores_low_and_asks_for_browns() -> None:
    data = BinData(
        material_additions=(
            _material("food_scraps"),
            _material("grass_clippings"),
            _material("coffee_grounds"),
        )
    )
    assessment = assess(data, NOW)

    balance = next(
        r for r in assessment.health.domains if r.name == "balance"
    )
    assert balance.score == 40
    assert balance.provenance is Provenance.INFERRED
    assert balance.reason_code == "greens_without_browns"
    assert balance.evidence[0].source == "materials_kb"
    assert balance.evidence[0].value == "3:0"

    assert assessment.health.score == 40
    assert assessment.health.evaluable_domains == ("balance",)
    assert assessment.health.provenance is Provenance.INFERRED
    # Confidence: 100 * (0.5 * 1/6 coverage + 0.5 * 2/3 support) = 41.67 → 42.
    assert assessment.confidence == 42

    assert assessment.action.code is ActionCode.ADD_BROWNS
    assert assessment.action.reason_code == "greens_without_browns"
    assert assessment.action.evidence[0].source == "materials_kb"


def test_all_brown_balance_scores_and_asks_for_greens() -> None:
    data = BinData(
        material_additions=(
            _material("dry_leaves"),
            _material("straw"),
            _material("cardboard"),
        )
    )
    assessment = assess(data, NOW)

    assert assessment.health.score == 55
    assert assessment.action.code is ActionCode.ADD_GREENS
    assert assessment.action.reason_code == "browns_without_greens"


def test_mixed_balance_is_healthy_and_needs_nothing() -> None:
    data = BinData(
        material_additions=(
            _material("food_scraps"),
            _material("food_scraps"),
            _material("dry_leaves"),
        )
    )
    assessment = assess(data, NOW)

    assert assessment.health.score == 85
    assert assessment.action.code is ActionCode.NONE
    assert assessment.action.reason_code == "no_issues_detected"


def test_too_few_materials_keeps_balance_unknown() -> None:
    assessment = assess(BinData(material_additions=(_material("food_scraps"),)), NOW)
    assert assessment.health.score is None
    assert assessment.health.provenance is Provenance.UNKNOWN
    assert assessment.health.evaluable_domains == ()


def test_unclassifiable_materials_never_produce_a_score() -> None:
    data = BinData(
        material_additions=(
            _material("mystery goo"),
            _material("another mystery"),
            _material("third mystery"),
        )
    )
    assessment = assess(data, NOW)
    assert assessment.health.score is None
    assert assessment.health.provenance is Provenance.UNKNOWN


def test_materials_outside_the_health_window_do_not_count() -> None:
    data = BinData(
        material_additions=(
            _material("food_scraps", days_ago=15.0),
            _material("food_scraps", days_ago=16.0),
            _material("food_scraps", days_ago=17.0),
        )
    )
    assessment = assess(data, NOW)
    assert assessment.health.score is None
    # The cycle itself is still ACTIVE: bookkeeping ≠ health.
    assert assessment.cycle_stage.value == "active"


# --- Aeration domain ---------------------------------------------------------


def test_adverse_odor_lowers_aeration() -> None:
    assessment = assess(BinData(observations=(_observation("sour smell"),)), NOW)

    aeration = next(
        r for r in assessment.health.domains if r.name == "aeration"
    )
    assert aeration.score == 45
    assert aeration.reason_code == "possible_poor_aeration"
    assert aeration.evidence[0].source == "user_observations"

    assert assessment.health.score == 45
    # An observed problem outranks the onboarding prompt.
    assert assessment.action.code is ActionCode.IMPROVE_AERATION
    assert assessment.action.reason_code == "possible_poor_aeration"


def test_multiple_distinct_adverse_signals_score_lower() -> None:
    data = BinData(
        observations=(
            _observation("sour smell"),
            _observation("compacted"),
        )
    )
    assessment = assess(data, NOW)
    aeration = next(
        r for r in assessment.health.domains if r.name == "aeration"
    )
    assert aeration.score == 25


def test_repeated_signal_counts_once() -> None:
    data = BinData(
        observations=(_observation("sour smell"), _observation("sour smell"))
    )
    assessment = assess(data, NOW)
    aeration = next(
        r for r in assessment.health.domains if r.name == "aeration"
    )
    assert aeration.score == 45


def test_positive_signals_raise_aeration() -> None:
    data = BinData(observations=(_observation("loose"),))
    assessment = assess(data, NOW)
    aeration = next(
        r for r in assessment.health.domains if r.name == "aeration"
    )
    assert aeration.score == 85
    assert aeration.reason_code == "appears_aerated"
    # No materials yet: the onboarding prompt still applies.
    assert assessment.action.code is ActionCode.LOG_FIRST_ADDITION


def test_never_complained_means_unknown_not_healthy() -> None:
    assessment = assess(BinData(observations=(_observation("damp"),)), NOW)
    aeration = next(
        r for r in assessment.health.domains if r.name == "aeration"
    )
    assert aeration.score is None
    assert assessment.health.score is None
    assert assessment.action.code is ActionCode.LOG_FIRST_ADDITION


def test_old_observations_fall_out_of_the_window() -> None:
    data = BinData(observations=(_observation("sour smell", days_ago=15.0),))
    assessment = assess(data, NOW)
    aeration = next(
        r for r in assessment.health.domains if r.name == "aeration"
    )
    assert aeration.score is None


# --- Aggregation and truthfulness -------------------------------------------


def test_domains_aggregate_into_one_honest_health_score() -> None:
    data = BinData(
        material_additions=(
            _material("food_scraps"),
            _material("grass_clippings"),
            _material("coffee_grounds"),
        ),
        observations=(_observation("sour smell"),),
    )
    assessment = assess(data, NOW)

    # round((40 + 45) / 2) = round(42.5) = 42.
    assert assessment.health.score == 42
    assert assessment.health.evaluable_domains == ("balance", "aeration")
    # The two sensor domains are explicitly reported as not evaluable here.
    assert assessment.health.limitations == (
        "domain_thermal_not_evaluable",
        "domain_moisture_not_evaluable",
    )
    # Confidence: 100 * (0.5 * 2/6 + 0.5 * 3/3) = 66.67 → 67.
    assert assessment.confidence == 67
    assert assessment.action.code is ActionCode.IMPROVE_AERATION

    # Evidence comes only from real, labelled sources — never a fake sensor.
    assert {item.source for item in assessment.evidence} == {
        "user_history",
        "materials_kb",
        "user_observations",
    }


def test_health_without_evidence_stays_unknown_with_domains_listed() -> None:
    assessment = assess(BinData(), NOW)
    assert assessment.health.score is None
    assert assessment.health.provenance is Provenance.UNKNOWN
    assert assessment.health.limitations == ("no_evaluable_domains",)
    assert [result.name for result in assessment.health.domains] == [
        "thermal",
        "moisture",
        "balance",
        "aeration",
    ]
    assert all(result.score is None for result in assessment.health.domains)


def test_interventions_alone_do_not_create_health_claims() -> None:
    data = BinData(
        interventions=(
            Intervention(timestamp=NOW, type=InterventionType.TURNING),
        )
    )
    assessment = assess(data, NOW)
    assert assessment.health.score is None
    assert assessment.health.provenance is Provenance.UNKNOWN
