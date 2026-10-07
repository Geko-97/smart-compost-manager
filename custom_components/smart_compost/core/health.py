"""Health domains and their evidence sources (M3 user data, M4 sensors).

Evaluable domains:

* ``thermal``  — current internal temperature, MEASURED via a bound sensor
  (stale or invalid readings drop back to UNKNOWN);
* ``moisture`` — current internal moisture, MEASURED via a bound sensor;
* ``balance``  — green/brown mix from classified material additions;
* ``aeration`` — inferred from observed odors and compaction signals
  (docs/12: aeration may be *inferred*, never measured without a sensor).

Domains without evidence stay UNKNOWN: an empty complaint history is not
proof of a healthy bin, and a sensor that stopped reporting is not a
measurement (docs/04, docs/06). The thermal domain also looks at the
time series (M5, docs/10): a fast rise at high temperature caps the
score, because "rapidly heating" is not "healthy" — it is heading
somewhere (docs/06: rapid heating).
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import datetime

from .constants import (
    AERATION_MULTIPLE_ADVERSE_SCORE,
    AERATION_ONE_ADVERSE_SCORE,
    AERATION_POSITIVE_ONLY_SCORE,
    BALANCE_ALL_BROWN_SCORE,
    BALANCE_ALL_GREEN_SCORE,
    BALANCE_MIN_MATERIALS,
    BALANCE_MIXED_SCORE,
    HEALTH_WINDOW,
    MOISTURE_BANDS,
    PHASE_THERMOPHILIC_CURRENT,
    SENSOR_STALE_AFTER,
    THERMAL_BANDS,
    THERMAL_FAST_RISE,
    THERMAL_FAST_RISE_SCORE_CAP,
)
from .evidence import Evidence
from .materials import MaterialCategory, classify_material
from .model import BinData, Capability, NumericValue, Provenance
from .temperature import TemperatureAnalysis

BALANCE_DOMAIN = "balance"
AERATION_DOMAIN = "aeration"
THERMAL_DOMAIN = "thermal"
MOISTURE_DOMAIN = "moisture"

_WHITESPACE_PATTERN = re.compile(r"\s+")

#: Exact normalized observation values that point at possible poor aeration:
#: sour/ammonia/rotten odors (anaerobic tendency) and waterlogged/compacted
#: structure. Pests are deliberately absent: they are not an aeration signal
#: (they get their own diagnosis in a later milestone).
ADVERSE_AERATION_SIGNALS = frozenset(
    {
        "sour",
        "sour smell",
        "sour odour",
        "vinegary",
        "ammonia",
        "ammonia smell",
        "rotten",
        "rancid",
        "putrid",
        "sewage",
        "anaerobic",
        "slimy",
        "soggy",
        "waterlogged",
        "soaked",
        "saturated",
        "muddy",
        "mud",
        "compacted",
        "compact",
    }
)

#: Exact normalized values that are positive evidence of air in the pile.
POSITIVE_AERATION_SIGNALS = frozenset(
    {
        "loose",
        "fluffy",
        "airy",
        "crumbly",
        "porous",
        "friable",
        "well aerated",
    }
)


@dataclass(frozen=True, slots=True)
class DomainResult:
    """Outcome of one health domain: a score, or honestly UNKNOWN."""

    name: str
    score: int | None
    provenance: Provenance
    reason_code: str | None
    evidence: tuple[Evidence, ...] = ()


def _unknown(name: str) -> DomainResult:
    return DomainResult(
        name=name, score=None, provenance=Provenance.UNKNOWN, reason_code=None
    )


def _normalize_signal(raw: str) -> str:
    return _WHITESPACE_PATTERN.sub(" ", raw.replace("_", " ").lower()).strip()


def _usable_measurement(
    value: NumericValue | None, now: datetime
) -> NumericValue | None:
    """A measurement counts only when it is present, finite and fresh.

    This is the engine's second line of defence: even if the HA layer passed
    a stale or invalid reading, the domain must not consume it.
    """
    if value is None or value.value is None or value.timestamp is None:
        return None
    if not math.isfinite(value.value):
        return None
    if (now - value.timestamp) > SENSOR_STALE_AFTER:
        return None
    return value


def _band(
    bands: tuple[tuple[float, int, str], ...], point: float
) -> tuple[int, str]:
    """First band whose (exclusive) upper bound contains the point.

    Tables always end with an `inf` ceiling, so the fallback below only
    satisfies the type checker for a malformed table.
    """
    for upper, score, reason in bands:
        if point < upper:
            return score, reason
    _, score, reason = bands[-1]
    return score, reason


def evaluate_thermal(
    data: BinData, now: datetime, analysis: TemperatureAnalysis
) -> DomainResult:
    """Current internal temperature against the compost heat bands.

    The current reading sets the band; the time series can only lower the
    score (a fast rise at high temperature is capped), never raise it —
    history corrects the present, it does not flatter it.
    """
    reading = _usable_measurement(data.internal_temperature, now)
    if reading is None or Capability.INTERNAL_TEMPERATURE not in data.capabilities:
        return _unknown(THERMAL_DOMAIN)

    score, reason = _band(THERMAL_BANDS, reading.value)
    evidence = [
        Evidence(
            source="sensor:internal_temperature",
            parameter="current_value",
            value=reading.value,
            timestamp=reading.timestamp,
            role="supports_domain_thermal",
        )
    ]

    slope = analysis.slope_per_hour
    if (
        slope is not None
        and slope >= THERMAL_FAST_RISE
        and reading.value >= PHASE_THERMOPHILIC_CURRENT
    ):
        score = min(score, THERMAL_FAST_RISE_SCORE_CAP)
        reason = "rapid_heating"
        evidence.append(
            Evidence(
                source="sensor:internal_temperature",
                parameter="trend_slope",
                value=round(slope, 2),
                timestamp=analysis.latest_timestamp or reading.timestamp,
                role="caps_domain_thermal",
            )
        )

    return DomainResult(
        name=THERMAL_DOMAIN,
        score=score,
        provenance=Provenance.INFERRED,
        reason_code=reason,
        evidence=tuple(evidence),
    )


def evaluate_moisture(data: BinData, now: datetime) -> DomainResult:
    """Current internal moisture against the compost moisture bands."""
    reading = _usable_measurement(data.internal_moisture, now)
    if reading is None or Capability.INTERNAL_MOISTURE not in data.capabilities:
        return _unknown(MOISTURE_DOMAIN)

    score, reason = _band(MOISTURE_BANDS, reading.value)
    return DomainResult(
        name=MOISTURE_DOMAIN,
        score=score,
        provenance=Provenance.INFERRED,
        reason_code=reason,
        evidence=(
            Evidence(
                source="sensor:internal_moisture",
                parameter="current_value",
                value=reading.value,
                timestamp=reading.timestamp,
                role="supports_domain_moisture",
            ),
        ),
    )


def evaluate_balance(data: BinData, now: datetime) -> DomainResult:
    """Green/brown balance from recent, classified material additions.

    Needs at least BALANCE_MIN_MATERIALS classified materials inside the
    health window; unclassifiable materials do not count (never guessed).
    """
    window = [
        addition
        for addition in data.material_additions
        if (now - addition.timestamp) <= HEALTH_WINDOW
    ]
    known = [
        (addition, classify_material(addition.material_type))
        for addition in window
    ]
    known = [
        (addition, category)
        for addition, category in known
        if category
        in (
            MaterialCategory.GREEN,
            MaterialCategory.BROWN,
            MaterialCategory.STRUCTURAL,
        )
    ]

    if len(known) < BALANCE_MIN_MATERIALS:
        return _unknown(BALANCE_DOMAIN)

    greens = sum(
        1 for _, category in known if category is MaterialCategory.GREEN
    )
    browns = sum(
        1
        for _, category in known
        if category in (MaterialCategory.BROWN, MaterialCategory.STRUCTURAL)
    )
    latest = max(addition.timestamp for addition, _ in known)
    evidence = (
        Evidence(
            source="materials_kb",
            parameter="green_brown_ratio",
            value=f"{greens}:{browns}",
            timestamp=latest,
            role="supports_domain_balance",
        ),
    )

    if greens and not browns:
        score, reason = BALANCE_ALL_GREEN_SCORE, "greens_without_browns"
    elif browns and not greens:
        score, reason = BALANCE_ALL_BROWN_SCORE, "browns_without_greens"
    else:
        score, reason = BALANCE_MIXED_SCORE, "balanced"

    return DomainResult(
        name=BALANCE_DOMAIN,
        score=score,
        provenance=Provenance.INFERRED,
        reason_code=reason,
        evidence=evidence,
    )


def evaluate_aeration(data: BinData, now: datetime) -> DomainResult:
    """Aeration from user-observed signals inside the health window.

    Adverse signals lower the score; only positive signals raise it; no
    relevant observation at all means UNKNOWN, never "fine".
    """
    adverse: set[str] = set()
    positive: set[str] = set()
    matched_timestamps: list[datetime] = []

    for observation in data.observations:
        if (now - observation.timestamp) > HEALTH_WINDOW:
            continue
        value = _normalize_signal(observation.value)
        if value in ADVERSE_AERATION_SIGNALS:
            adverse.add(value)
            matched_timestamps.append(observation.timestamp)
        elif value in POSITIVE_AERATION_SIGNALS:
            positive.add(value)
            matched_timestamps.append(observation.timestamp)

    if not adverse and not positive:
        return _unknown(AERATION_DOMAIN)

    latest = max(matched_timestamps)
    if adverse:
        score = (
            AERATION_ONE_ADVERSE_SCORE
            if len(adverse) == 1
            else AERATION_MULTIPLE_ADVERSE_SCORE
        )
        reason = "possible_poor_aeration"
        value: str | int = len(adverse)
    else:
        score = AERATION_POSITIVE_ONLY_SCORE
        reason = "appears_aerated"
        value = len(positive)

    return DomainResult(
        name=AERATION_DOMAIN,
        score=score,
        provenance=Provenance.INFERRED,
        reason_code=reason,
        evidence=(
            Evidence(
                source="user_observations",
                parameter="aeration_signals",
                value=value,
                timestamp=latest,
                role="supports_domain_aeration",
            ),
        ),
    )
