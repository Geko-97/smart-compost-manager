"""Thermal history in the assessment (M5): trends, phase, diagnostics.

The engine may only correct the thermal score DOWNWARD with history, the
`no_temperature_trend` limitation must disappear once the evidence is
enough, and phase/diagnostics carry their own confidence without ever
padding the triade (docs/06, docs/07, docs/10).

Expected numbers are hand-computed from `core/constants.py`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from custom_components.smart_compost.core.assessment import BinData, assess
from custom_components.smart_compost.core.constants import (
    THERMAL_FAST_RISE_SCORE_CAP,
)
from custom_components.smart_compost.core.model import (
    Capability,
    NumericValue,
    Provenance,
)
from custom_components.smart_compost.core.temperature import TrendDirection

NOW = datetime(2026, 10, 6, 12, 0, 0, tzinfo=UTC)


def _sample(minutes_ago: float, value: float) -> NumericValue:
    return NumericValue(
        value=value,
        unit="°C",
        provenance=Provenance.MEASURED,
        timestamp=NOW - timedelta(minutes=minutes_ago),
    )


def _data(
    samples: tuple[NumericValue, ...], current_value: float | None
) -> BinData:
    capabilities = {Capability.MANUAL_DATA}
    temperature: NumericValue | None = None
    if current_value is not None:
        capabilities.add(Capability.INTERNAL_TEMPERATURE)
        temperature = _sample(1.0, current_value)
    return BinData(
        capabilities=frozenset(capabilities),
        internal_temperature=temperature,
        temperature_history=samples,
    )


def _rising_history() -> tuple[NumericValue, ...]:
    """7 samples over 2 h rising 30 → 42 °C (6 °C/h ≥ THERMAL_FAST_RISE)."""
    return tuple(
        _sample(minutes_ago, 30.0 + (120 - minutes_ago) * 0.1)
        for minutes_ago in (120, 100, 80, 60, 40, 20, 0)
    )


def test_fast_rise_at_high_temperature_caps_the_thermal_score() -> None:
    assessment = assess(_data(_rising_history(), 42.0), NOW)

    thermal = next(r for r in assessment.health.domains if r.name == "thermal")
    # Band for 42 °C would be 90; the fast rise caps it (docs/06).
    assert thermal.score == THERMAL_FAST_RISE_SCORE_CAP == 55
    assert thermal.reason_code == "rapid_heating"
    # The cap explains itself through evidence (docs/06 §9, why view).
    assert thermal.evidence[1].parameter == "trend_slope"
    assert thermal.evidence[1].value == 6.0
    assert thermal.evidence[1].role == "caps_domain_thermal"

    # The only evaluable domain, so health mirrors it.
    assert assessment.health.score == 55
    assert assessment.health.evaluable_domains == ("thermal",)

    # Enough history: the static limitation is gone (docs/10).
    assert "no_temperature_trend" not in assessment.health.limitations

    analysis = assessment.temperature_analysis
    assert analysis.sample_count == 7
    assert analysis.trend is TrendDirection.RISING
    assert analysis.slope_per_hour == pytest.approx(6.0)


def test_the_diagnosis_follows_the_cap_with_its_own_confidence() -> None:
    assessment = assess(_data(_rising_history(), 42.0), NOW)

    assert [item.code for item in assessment.diagnostics] == ["rapid_heating"]
    finding = assessment.diagnostics[0]
    assert finding.confidence == 70  # two signals: fast_rise + elevated_now
    assert finding.signals == ("fast_rise", "elevated_now")

    # Phase stays honest: one signal (current_high) is not a phase.
    assert assessment.phase.phase is None
    assert assessment.phase.provenance is Provenance.UNKNOWN
    assert assessment.phase.limitations == ("insufficient_phase_evidence",)

    # The triade counts stage + thermal evidences ONLY: diagnostics never
    # pad the confidence (docs/06: confidence ≠ the number of findings).
    assert [item.parameter for item in assessment.evidence] == [
        "material_additions_count",
        "current_value",
        "trend_slope",
    ]
    # Confidence: 100 * (0.5 * 1/6 domain coverage + 0.5 * 3/3 support) = 58.
    assert assessment.confidence == 58
    # DQ: 100 * (0.5 * 1/2 measured coverage) = 25.
    assert assessment.data_quality == 25


def test_too_little_history_keeps_the_trend_limitation_and_no_cap() -> None:
    # 3 samples: no slope, so no cap and no trend claim (docs/06).
    samples = (_sample(30, 42.0), _sample(20, 42.0), _sample(10, 42.0))
    assessment = assess(_data(samples, 42.0), NOW)

    thermal = next(r for r in assessment.health.domains if r.name == "thermal")
    assert thermal.score == 90  # band for 42 °C, untouched
    assert thermal.reason_code == "thermophilic"
    assert "no_temperature_trend" in assessment.health.limitations
    assert assessment.diagnostics == ()
    assert assessment.phase.phase is None  # peak 42 < 45: one signal only
    assert assessment.temperature_analysis.slope_per_hour is None


def test_history_assessments_are_pure_and_deterministic() -> None:
    bin_a = _data(_rising_history(), 42.0)
    bin_b = _data((), None)

    first = assess(bin_a, NOW)
    assess(bin_b, NOW)  # assessing another bin must not leak anything
    second = assess(bin_a, NOW)

    assert first == second
    assert assess(bin_b, NOW).temperature_analysis.sample_count == 0
    assert assess(bin_b, NOW).diagnostics == ()
    assert assess(bin_b, NOW).phase.phase is None
