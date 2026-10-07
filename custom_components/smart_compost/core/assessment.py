"""Assessment engine — zero-sensor capable baseline (M1) + health domains (M3)
+ thermal history (M5).

The three scores are computed by separate functions with separate inputs so
they can never collapse into three variants of one number (docs/06):

* ``_data_quality``   — how complete, continuous and fresh the inputs are;
* ``_confidence``     — how well-supported our conclusions are;
* ``_health``         — how healthy the process looks, domain by domain.

Domains without evidence stay UNKNOWN and are excluded from the health
average (never padded), which in turn keeps the confidence coverage honest.

M5 adds the thermal time series (docs/10): the same history feeds the
trend correction of the thermal domain, the phase inference (docs/07) and
the multi-signal diagnostics (docs/06). Phase and diagnostics carry their
OWN signal-count confidence — they never pad the triade's confidence.

The engine is pure: everything it may look at arrives as ``BinData`` plus an
injected ``now``. No sensor access, no global state, no wall clock inside the
formulas — which makes assessments deterministic, unit-testable, and
automatically isolated per bin (docs/11).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from .advanced import diagnose_signals
from .constants import (
    AERATION_ACTION_THRESHOLD,
    BASELINE_MEASURABLE_SIGNALS,
    DQ_FRESHNESS_WEIGHT,
    DQ_INTERVENTION_SHARE,
    DQ_MATERIAL_SHARE,
    DQ_MEASUREMENT_WEIGHT,
    DQ_OBSERVATION_SHARE,
    DQ_USER_DATA_WEIGHT,
    FRESH_WINDOW,
    MAX_COUNTED_EVIDENCE,
    STALE_WINDOW,
    TOTAL_DECISION_DOMAINS,
    WEIGHT_DOMAIN_COVERAGE,
    WEIGHT_EVIDENCE_SUPPORT,
)
from .cycle import (
    Baseline,
    CycleComparison,
    CycleReport,
    build_baseline,
    build_comparison,
    build_report,
    select_previous,
    select_report,
)
from .diagnostics import Diagnostic, diagnose
from .evidence import Evidence
from .health import (
    AERATION_DOMAIN,
    BALANCE_DOMAIN,
    MOISTURE_DOMAIN,
    THERMAL_DOMAIN,
    DomainResult,
    evaluate_aeration,
    evaluate_balance,
    evaluate_moisture,
    evaluate_thermal,
)
from .maturity import MaturityResult, assess_maturity
from .model import (
    ActionCode,
    BinData,
    Capability,
    CycleStage,
    Provenance,
    Severity,
)
from .phase import PhaseResult, detect_phase
from .temperature import TemperatureAnalysis, analyze


@dataclass(frozen=True, slots=True)
class HealthResult:
    """How healthy the process looks — distinct from confidence and DQ.

    `score is None` means "not evaluable with what we have" (UNKNOWN). The
    HA layer renders that as an unknown state, never as 0 (which would be a
    claim). `domains` carries every evaluated domain — including the UNKNOWN
    ones — so the UI can explain exactly what was and was not considered.
    """

    score: int | None
    provenance: Provenance
    domains: tuple[DomainResult, ...] = ()
    limitations: tuple[str, ...] = ()

    @property
    def evaluable_domains(self) -> tuple[str, ...]:
        """Domains that produced a score; UNKNOWN domains are excluded."""
        return tuple(
            result.name for result in self.domains if result.score is not None
        )


@dataclass(frozen=True, slots=True)
class RecommendedAction:
    """The single priority action for the main screen (docs/19)."""

    code: ActionCode
    severity: Severity
    reason_code: str
    confidence: int
    evidence: tuple[Evidence, ...]


@dataclass(frozen=True, slots=True)
class Assessment:
    """The complete assessment of one bin at one instant."""

    assessed_at: datetime
    health: HealthResult
    confidence: int
    data_quality: int
    cycle_stage: CycleStage
    action: RecommendedAction
    evidence: tuple[Evidence, ...]
    limitations: tuple[str, ...]
    phase: PhaseResult
    temperature_analysis: TemperatureAnalysis
    maturity: MaturityResult
    diagnostics: tuple[Diagnostic, ...] = ()
    cycle_report: CycleReport | None = None
    cycle_comparison: CycleComparison | None = None
    baseline: Baseline | None = None


def assess(data: BinData, now: datetime) -> Assessment:
    """Evaluate one bin at `now`.

    `now` must be timezone-aware (docs/24: naive datetimes are a bug, not a
    convenience).
    """
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be a timezone-aware datetime")

    analysis = analyze(data.temperature_history, now)
    stage, evidence = _cycle_stage(data, now)
    health, domain_evidence = _health(data, now, analysis)
    evidence.extend(domain_evidence)
    confidence = _confidence(evidence, health, now)
    data_quality = _data_quality(data, now)
    action = _action(stage, confidence, evidence, health)
    phase = detect_phase(data, analysis, now)
    # Thermal findings first, then the advanced signals (M9): both follow
    # the same two-signal rule, so their codes can live in one list.
    diagnostics = diagnose(data, analysis, now) + diagnose_signals(data, analysis, now)

    # Cycle report / comparison / baseline: same-bin facts only (docs/11 §2).
    reports = tuple(build_report(cycle, data, now) for cycle in data.cycles)
    cycle_report = select_report(reports)
    cycle_comparison = None
    if cycle_report is not None:
        previous_report = select_previous(reports, cycle_report)
        if previous_report is not None:
            cycle_comparison = build_comparison(cycle_report, previous_report)
    baseline = build_baseline(reports)

    # Maturity (M8) is a different question from the phase: it needs the
    # baseline for a PERSONAL forecast window (docs/07, docs/18 §7).
    maturity = assess_maturity(data, analysis, now, baseline)

    limitations = list(health.limitations)
    if Capability.INTERNAL_TEMPERATURE not in data.capabilities:
        limitations.append("no_internal_temperature")
    if Capability.INTERNAL_MOISTURE not in data.capabilities:
        limitations.append("no_internal_moisture")

    return Assessment(
        assessed_at=now,
        health=health,
        confidence=confidence,
        data_quality=data_quality,
        cycle_stage=stage,
        action=action,
        evidence=tuple(evidence),
        limitations=tuple(limitations),
        phase=phase,
        temperature_analysis=analysis,
        maturity=maturity,
        diagnostics=diagnostics,
        cycle_report=cycle_report,
        cycle_comparison=cycle_comparison,
        baseline=baseline,
    )


def _cycle_stage(data: BinData, now: datetime) -> tuple[CycleStage, list[Evidence]]:
    """Bookkeeping stage from user history alone.

    A cycle exists once material has been logged; before that the bin is NEW
    and the honest advice is to log the first addition.
    """
    if not data.material_additions:
        return CycleStage.NEW, [
            Evidence(
                source="user_history",
                parameter="material_additions_count",
                value=0,
                timestamp=now,
                role="supports_stage_new",
            )
        ]

    latest = max(addition.timestamp for addition in data.material_additions)
    return CycleStage.ACTIVE, [
        Evidence(
            source="user_history",
            parameter="material_additions_count",
            value=len(data.material_additions),
            timestamp=latest,
            role="supports_stage_active",
        )
    ]


def _health(
    data: BinData, now: datetime, analysis: TemperatureAnalysis
) -> tuple[HealthResult, list[Evidence]]:
    """Aggregate the health domains (docs/06).

    Only domains with real evidence contribute a score. UNKNOWN domains are
    excluded from the average — never padded with a default — and show up
    instead as limitations and in the confidence domain coverage.
    """
    domains = (
        evaluate_thermal(data, now, analysis),
        evaluate_moisture(data, now),
        evaluate_balance(data, now),
        evaluate_aeration(data, now),
    )
    evidence = [item for result in domains for item in result.evidence]
    evaluable = [result for result in domains if result.score is not None]

    if not evaluable:
        return (
            HealthResult(
                score=None,
                provenance=Provenance.UNKNOWN,
                domains=domains,
                limitations=("no_evaluable_domains",),
            ),
            evidence,
        )

    score = round(sum(result.score for result in evaluable) / len(evaluable))
    limitations = tuple(
        f"domain_{result.name}_not_evaluable"
        for result in domains
        if result.score is None
    )
    if any(
        result.name == THERMAL_DOMAIN and result.score is not None
        for result in domains
    ) and not analysis.supports_trend:
        # Honest framing: the current reading is the current state, and
        # without TREND_MIN_SAMPLES + TREND_MIN_SPAN there is no trend to
        # claim (docs/06: insufficient evidence → UNKNOWN, docs/10).
        limitations += ("no_temperature_trend",)
    return (
        HealthResult(
            score=score,
            provenance=Provenance.INFERRED,
            domains=domains,
            limitations=limitations,
        ),
        evidence,
    )


def _confidence(
    evidence: Sequence[Evidence], health: HealthResult, now: datetime
) -> int:
    """How well-supported our conclusions are (docs/06, never the same as DQ).

    Combines domain coverage (how much of the decision model can be evaluated
    at all) with evidence support (how many fresh pieces of evidence back the
    current conclusions).
    """
    domain_coverage = len(health.evaluable_domains) / TOTAL_DECISION_DOMAINS
    newest = max(item.timestamp for item in evidence)
    support = (
        min(len(evidence), MAX_COUNTED_EVIDENCE) / MAX_COUNTED_EVIDENCE
    ) * _freshness(newest, now)
    return round(
        100
        * (
            WEIGHT_DOMAIN_COVERAGE * domain_coverage
            + WEIGHT_EVIDENCE_SUPPORT * support
        )
    )


def _data_quality(data: BinData, now: datetime) -> int:
    """How complete, continuous and fresh the inputs are (docs/06).

    Three independent components: measured-signal coverage, breadth of user
    data, and freshness of the most recent user input. Zero sensors and no
    history honestly yields 0.
    """
    measured = sum(
        1
        for capability in (
            Capability.INTERNAL_TEMPERATURE,
            Capability.INTERNAL_MOISTURE,
        )
        if capability in data.capabilities
    )
    measurement_coverage = measured / BASELINE_MEASURABLE_SIGNALS

    user_score = 0.0
    if data.material_additions:
        user_score += DQ_MATERIAL_SHARE
    if data.observations:
        user_score += DQ_OBSERVATION_SHARE
    if data.interventions:
        user_score += DQ_INTERVENTION_SHARE

    latest = _latest_user_event(data)
    freshness = _freshness(latest, now) if latest is not None else 0.0

    return round(
        100
        * (
            DQ_MEASUREMENT_WEIGHT * measurement_coverage
            + DQ_USER_DATA_WEIGHT * user_score
            + DQ_FRESHNESS_WEIGHT * freshness
        )
    )


def _action(
    stage: CycleStage,
    confidence: int,
    evidence: Sequence[Evidence],
    health: HealthResult,
) -> RecommendedAction:
    """Single priority action (docs/19: one action on the main screen).

    Priority: measured moisture extremes and observed aeration problems first
    (current issues), then the onboarding prompt, then balance corrections,
    then nothing to do.
    """
    by_name = {result.name: result for result in health.domains}

    moisture = by_name.get(MOISTURE_DOMAIN)
    if moisture is not None and moisture.reason_code == "too_dry":
        return RecommendedAction(
            code=ActionCode.WATER_COMPOST,
            severity=Severity.SUGGESTION,
            reason_code="too_dry",
            confidence=confidence,
            evidence=moisture.evidence,
        )

    aeration = by_name.get(AERATION_DOMAIN)
    if (
        aeration is not None
        and aeration.score is not None
        and aeration.score < AERATION_ACTION_THRESHOLD
    ):
        return RecommendedAction(
            code=ActionCode.IMPROVE_AERATION,
            severity=Severity.SUGGESTION,
            reason_code="possible_poor_aeration",
            confidence=confidence,
            evidence=aeration.evidence,
        )

    if moisture is not None and moisture.reason_code == "too_wet":
        return RecommendedAction(
            code=ActionCode.ADD_BROWNS,
            severity=Severity.SUGGESTION,
            reason_code="too_wet",
            confidence=confidence,
            evidence=moisture.evidence,
        )

    if stage is CycleStage.NEW:
        return RecommendedAction(
            code=ActionCode.LOG_FIRST_ADDITION,
            severity=Severity.SUGGESTION,
            reason_code="no_materials_logged",
            confidence=confidence,
            evidence=tuple(evidence),
        )

    balance = by_name.get(BALANCE_DOMAIN)
    if balance is not None and balance.reason_code in (
        "greens_without_browns",
        "browns_without_greens",
    ):
        code = (
            ActionCode.ADD_BROWNS
            if balance.reason_code == "greens_without_browns"
            else ActionCode.ADD_GREENS
        )
        return RecommendedAction(
            code=code,
            severity=Severity.SUGGESTION,
            reason_code=balance.reason_code,
            confidence=confidence,
            evidence=balance.evidence,
        )

    return RecommendedAction(
        code=ActionCode.NONE,
        severity=Severity.INFO,
        reason_code="no_issues_detected",
        confidence=confidence,
        evidence=tuple(evidence),
    )


def _latest_user_event(data: BinData) -> datetime | None:
    """Timestamp of the most recent user input, if any."""
    timestamps = [
        item.timestamp
        for group in (
            data.material_additions,
            data.observations,
            data.interventions,
        )
        for item in group
    ]
    return max(timestamps) if timestamps else None


def _freshness(timestamp: datetime, now: datetime) -> float:
    """Recency factor: 1.0 fresh, 0.5 ageing, 0.0 stale."""
    age = now - timestamp
    if age <= FRESH_WINDOW:
        return 1.0
    if age <= STALE_WINDOW:
        return 0.5
    return 0.0
