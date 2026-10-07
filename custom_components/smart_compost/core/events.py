"""Domain events (M6, docs/10).

Every event carries the metadata docs/10 §4 requires: timestamp, bin_id,
cycle_id, type, source — plus before/after states and a reason where they
add meaning. Origin distinguishes what a human logged from what the engine
detected (docs/10 §5).

Events are facts, not opinions: they fire on observable transitions and
never on a timer, so a quiet bin produces nothing. The first assessment
after (re)start is a baseline, never a transition — a reload must neither
lose nor duplicate domain history (PR-027).

Not every documented event type exists yet: `anomaly` has no detection
milestone behind it, so it stays deliberately absent rather than faked
(docs/10 §2: events are curated, not a raw dump).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum

from .assessment import Assessment
from .constants import (
    EVENT_PEAK_MIN_RISE,
    HEALTH_BAND_FAIR_MAX,
    HEALTH_BAND_POOR_MAX,
    MAX_STORED_EVENTS,
    PHASE_PEAK_SIGNIFICANT,
)
from .model import CycleStage, CycleStatus


class EventType(StrEnum):
    """Event vocabulary (docs/10 §2, at least these)."""

    # Manual logs (origin MANUAL).
    MATERIAL_ADDED = "material_added"
    OBSERVATION = "observation"
    WATERING = "watering"
    TURNING = "turning"
    AERATION = "aeration"
    MANUAL_CORRECTION = "manual_correction"
    INTERVENTION_LOGGED = "intervention_logged"
    # Cycle lifecycle (origin depends on who invoked the service).
    CYCLE_STARTED = "cycle_started"
    CYCLE_COMPLETED = "cycle_completed"
    # Engine-detected transitions (origin INTEGRATION).
    PHASE_CHANGED = "phase_changed"
    MATURITY_ESTIMATED = "maturity_estimated"
    TEMPERATURE_PEAK = "temperature_peak"
    RAPID_HEATING = "rapid_heating"
    RAPID_COOLING = "rapid_cooling"
    HEALTH_CHANGED = "health_changed"


class EventOrigin(StrEnum):
    """Who caused the event (docs/10 §5)."""

    MANUAL = "manual"
    AUTOMATION = "automation"
    INTEGRATION = "integration"


@dataclass(frozen=True, slots=True)
class CompostEvent:
    """One thing that happened to one bin (docs/10 §4).

    `cycle_id` stays None until cycles get stable ids; None is the honest
    representation of "unknown", never a fabricated id.
    """

    timestamp: datetime
    type: EventType
    origin: EventOrigin
    bin_id: str | None = None
    cycle_id: str | None = None
    before_state: str | None = None
    after_state: str | None = None
    reason: str | None = None
    notes: str | None = None


def health_band(score: int | None) -> str | None:
    """Map a health score to its band — None stays UNKNOWN (docs/06 §3)."""
    if score is None:
        return None
    if score < HEALTH_BAND_POOR_MAX:
        return "poor"
    if score < HEALTH_BAND_FAIR_MAX:
        return "fair"
    return "good"


def bounded_events(events: tuple[CompostEvent, ...]) -> tuple[CompostEvent, ...]:
    """Keep the newest MAX_STORED_EVENTS (oldest age out first)."""
    if len(events) <= MAX_STORED_EVENTS:
        return events
    return events[-MAX_STORED_EVENTS:]


def _with_bin(event: CompostEvent, bin_id: str | None) -> CompostEvent:
    return event if bin_id is None else replace(event, bin_id=bin_id)


def material_event(
    timestamp: datetime, material_type: str, notes: str | None, bin_id: str | None
) -> CompostEvent:
    """A logged material addition (origin MANUAL)."""
    return _with_bin(
        CompostEvent(
            timestamp=timestamp,
            type=EventType.MATERIAL_ADDED,
            origin=EventOrigin.MANUAL,
            reason=material_type,
            notes=notes,
        ),
        bin_id,
    )


def observation_event(
    timestamp: datetime, category: str, value: str, notes: str | None,
    bin_id: str | None,
) -> CompostEvent:
    """A logged observation (origin MANUAL)."""
    return _with_bin(
        CompostEvent(
            timestamp=timestamp,
            type=EventType.OBSERVATION,
            origin=EventOrigin.MANUAL,
            reason=f"{category}:{value}",
            notes=notes,
        ),
        bin_id,
    )


#: Intervention types with their own documented event name; the rest fall
#: back to a generic event instead of inventing a type (docs/10 §2).
_INTERVENTION_EVENT_TYPES = {
    "watering": EventType.WATERING,
    "turning": EventType.TURNING,
    "aeration": EventType.AERATION,
    "correction": EventType.MANUAL_CORRECTION,
}

#: Diagnostics that have their own documented event name; other findings
#: stay findings (docs/10 §2: events are curated, not a raw dump).
_DIAGNOSTIC_EVENT_TYPES = {
    "rapid_heating": EventType.RAPID_HEATING,
    "rapid_cooling": EventType.RAPID_COOLING,
}


def intervention_event(
    timestamp: datetime, intervention_type: str, notes: str | None,
    bin_id: str | None,
) -> CompostEvent:
    """A logged intervention (origin MANUAL, type when documented)."""
    return _with_bin(
        CompostEvent(
            timestamp=timestamp,
            type=_INTERVENTION_EVENT_TYPES.get(
                intervention_type, EventType.INTERVENTION_LOGGED
            ),
            origin=EventOrigin.MANUAL,
            reason=intervention_type,
            notes=notes,
        ),
        bin_id,
    )


def cycle_started_event(
    timestamp: datetime,
    bin_id: str | None,
    cycle_id: str,
    origin: EventOrigin,
) -> CompostEvent:
    """A batch cycle was started explicitly (service call)."""
    return CompostEvent(
        timestamp=timestamp,
        type=EventType.CYCLE_STARTED,
        origin=origin,
        bin_id=bin_id,
        cycle_id=cycle_id,
        after_state=CycleStatus.ACTIVE.value,
        reason="cycle_started",
    )


def cycle_completed_event(
    timestamp: datetime,
    bin_id: str | None,
    cycle_id: str,
    origin: EventOrigin,
    has_output: bool,
) -> CompostEvent:
    """A batch cycle was completed (optionally with an output report)."""
    return CompostEvent(
        timestamp=timestamp,
        type=EventType.CYCLE_COMPLETED,
        origin=origin,
        bin_id=bin_id,
        cycle_id=cycle_id,
        before_state=CycleStatus.ACTIVE.value,
        after_state=CycleStatus.COMPLETED.value,
        reason="output_logged" if has_output else None,
    )


def transition_events(
    previous: Assessment | None,
    current: Assessment,
    now: datetime,
    bin_id: str | None,
) -> tuple[CompostEvent, ...]:
    """Detect what changed between two consecutive assessments.

    `previous is None` means baseline (first assessment after setup or
    reload): no transition can be claimed without the "before" side, so
    nothing fires (docs/04: never invent the other half of a comparison).
    """
    if previous is None:
        return ()

    events: list[CompostEvent] = []

    # An explicitly started cycle already reported its own cycle_started;
    # the bookkeeping stage crossing must not claim it a second time.
    explicit_cycle_active = (
        current.cycle_report is not None
        and current.cycle_report.status is CycleStatus.ACTIVE
    )
    if (
        previous.cycle_stage is CycleStage.NEW
        and current.cycle_stage is not CycleStage.NEW
        and not explicit_cycle_active
    ):
        events.append(
            CompostEvent(
                timestamp=now,
                type=EventType.CYCLE_STARTED,
                origin=EventOrigin.INTEGRATION,
                bin_id=bin_id,
                before_state="new",
                after_state="active",
                reason="first_material_logged",
            )
        )

    previous_phase = previous.phase.phase
    current_phase = current.phase.phase
    if previous_phase is not current_phase:
        events.append(
            CompostEvent(
                timestamp=now,
                type=EventType.PHASE_CHANGED,
                origin=EventOrigin.INTEGRATION,
                bin_id=bin_id,
                before_state=previous_phase.value if previous_phase else "unknown",
                after_state=current_phase.value if current_phase else "unknown",
            )
        )

    previous_maturity = previous.maturity.state
    current_maturity = current.maturity.state
    if previous_maturity is not current_maturity:
        events.append(
            CompostEvent(
                timestamp=now,
                type=EventType.MATURITY_ESTIMATED,
                origin=EventOrigin.INTEGRATION,
                bin_id=bin_id,
                before_state=(
                    previous_maturity.value if previous_maturity else "unknown"
                ),
                after_state=(
                    current_maturity.value if current_maturity else "unknown"
                ),
                reason="readiness_changed",
            )
        )

    previous_peak = previous.temperature_analysis.peak_value
    current_peak = current.temperature_analysis.peak_value
    if (
        previous_peak is not None
        and current_peak is not None
        and previous_peak < PHASE_PEAK_SIGNIFICANT <= current_peak
        and current_peak >= previous_peak + EVENT_PEAK_MIN_RISE
    ):
        events.append(
            CompostEvent(
                timestamp=now,
                type=EventType.TEMPERATURE_PEAK,
                origin=EventOrigin.INTEGRATION,
                bin_id=bin_id,
                before_state=f"{previous_peak:.1f}",
                after_state=f"{current_peak:.1f}",
                reason="significant_peak_reached",
            )
        )

    previous_findings = {item.code for item in previous.diagnostics}
    for finding in current.diagnostics:
        if finding.code in previous_findings:
            continue
        event_type = _DIAGNOSTIC_EVENT_TYPES.get(finding.code)
        if event_type is None:
            # A diagnostic without a documented event name simply does not
            # produce an event — the vocabulary stays curated (docs/10).
            continue
        events.append(
            CompostEvent(
                timestamp=now,
                type=event_type,
                origin=EventOrigin.INTEGRATION,
                bin_id=bin_id,
                after_state=finding.code,
                reason="+".join(finding.signals),
            )
        )

    previous_band = health_band(previous.health.score)
    current_band = health_band(current.health.score)
    if current_band is not None and previous_band is not None:
        if current_band != previous_band:
            events.append(
                CompostEvent(
                    timestamp=now,
                    type=EventType.HEALTH_CHANGED,
                    origin=EventOrigin.INTEGRATION,
                    bin_id=bin_id,
                    before_state=previous_band,
                    after_state=current_band,
                    reason=f"score_{previous.health.score}_{current.health.score}",
                )
            )

    return tuple(events)
