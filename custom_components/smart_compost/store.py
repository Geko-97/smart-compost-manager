"""Per-bin persistence (docs/19_DATA_STORAGE.md).

Only what Home Assistant does not store itself: the user's log of
materials, observations and interventions, the bounded temperature series,
the bounded event history and the notification engine state (cooldowns
must survive a restart, docs/26 §6) — one Store per config entry so bins
can never read each other's history. Invalid stored records are skipped
with a warning — one corrupt record must not take the whole history down,
and silently dropping data is never done without a log line.

Schema evolution is additive: a missing key loads as its default, so old
stores keep working without a version bump (docs/19 §7).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import DOMAIN
from .core.events import CompostEvent, EventOrigin, EventType
from .core.model import (
    Cycle,
    CycleStatus,
    Intervention,
    InterventionType,
    MaterialAddition,
    NumericValue,
    ObservationCategory,
    Output,
    Provenance,
    QuantityPrecision,
    Severity,
    UserObservation,
)
from .core.notifications import CategoryState, NotificationCategory

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1


@dataclass(frozen=True, slots=True)
class BinRecords:
    """The persisted history of one bin."""

    materials: tuple[MaterialAddition, ...] = ()
    observations: tuple[UserObservation, ...] = ()
    interventions: tuple[Intervention, ...] = ()
    temperature: tuple[NumericValue, ...] = ()
    cycles: tuple[Cycle, ...] = ()
    events: tuple[CompostEvent, ...] = ()
    #: Pairs of (category value, engine state), sorted for stable writes.
    notification_states: tuple[tuple[str, CategoryState], ...] = ()


class BinStore:
    """JSON store for one config entry (one compost bin)."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self._store = Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry_id}")

    async def async_load(self) -> BinRecords:
        """Load the history; unreadable storage raises, bad records are skipped."""
        raw = await self._store.async_load()
        if not isinstance(raw, dict):
            if raw is not None:
                _LOGGER.warning("Stored history has unexpected shape; starting empty")
            return BinRecords()

        return BinRecords(
            materials=_load_list(raw.get("materials"), "material", _material_from_dict),
            observations=_load_list(
                raw.get("observations"), "observation", _observation_from_dict
            ),
            interventions=_load_list(
                raw.get("interventions"), "intervention", _intervention_from_dict
            ),
            temperature=_load_list(
                raw.get("temperature"), "temperature_sample", _temperature_from_dict
            ),
            cycles=_load_list(raw.get("cycles"), "cycle", _cycle_from_dict),
            events=_load_list(raw.get("events"), "event", _event_from_dict),
            notification_states=_notification_states_from_raw(
                raw.get("notification_states")
            ),
        )

    async def async_save(self, records: BinRecords) -> None:
        """Persist the full history of one bin."""
        await self._store.async_save(
            {
                "materials": [_material_to_dict(item) for item in records.materials],
                "observations": [
                    _observation_to_dict(item) for item in records.observations
                ],
                "interventions": [
                    _intervention_to_dict(item) for item in records.interventions
                ],
                "temperature": [
                    _temperature_to_dict(item) for item in records.temperature
                ],
                "cycles": [_cycle_to_dict(item) for item in records.cycles],
                "events": [_event_to_dict(item) for item in records.events],
                "notification_states": {
                    key: _state_to_dict(state)
                    for key, state in records.notification_states
                },
            }
        )


def _load_list(raw: object, label: str, parser) -> tuple:
    """Parse one record list, skipping (and logging) anything corrupt."""
    if raw is None:
        return ()
    if not isinstance(raw, list):
        _LOGGER.warning("Stored %s list has unexpected shape; ignoring it", label)
        return ()

    parsed = []
    for index, item in enumerate(raw):
        try:
            parsed.append(parser(item))
        except (KeyError, TypeError, ValueError):
            _LOGGER.warning(
                "Skipping invalid stored %s #%s", label, index, exc_info=True
            )
    return tuple(parsed)


def _parse_timestamp(raw: object) -> datetime:
    if not isinstance(raw, str):
        raise ValueError("timestamp must be a string")
    moment = datetime.fromisoformat(raw)
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return moment


def _optional_str(raw: object) -> str | None:
    return None if raw is None else str(raw)


def _optional_float(raw: object) -> float | None:
    return None if raw is None else float(raw)


def _optional_int(raw: object) -> int | None:
    return None if raw is None else int(raw)


def _material_from_dict(raw: object) -> MaterialAddition:
    if not isinstance(raw, dict):
        raise TypeError("material record must be an object")
    return MaterialAddition(
        timestamp=_parse_timestamp(raw["timestamp"]),
        material_type=str(raw["material_type"]),
        quantity_value=_optional_float(raw.get("quantity_value")),
        quantity_unit=_optional_str(raw.get("quantity_unit")),
        quantity_precision=QuantityPrecision(raw["quantity_precision"]),
        notes=_optional_str(raw.get("notes")),
    )


def _material_to_dict(record: MaterialAddition) -> dict:
    return {
        "timestamp": record.timestamp.isoformat(),
        "material_type": record.material_type,
        "quantity_value": record.quantity_value,
        "quantity_unit": record.quantity_unit,
        "quantity_precision": record.quantity_precision.value,
        "notes": record.notes,
    }


def _observation_from_dict(raw: object) -> UserObservation:
    if not isinstance(raw, dict):
        raise TypeError("observation record must be an object")
    return UserObservation(
        timestamp=_parse_timestamp(raw["timestamp"]),
        category=ObservationCategory(raw["category"]),
        value=str(raw["value"]),
        severity=Severity(raw.get("severity", Severity.INFO.value)),
        notes=_optional_str(raw.get("notes")),
    )


def _observation_to_dict(record: UserObservation) -> dict:
    return {
        "timestamp": record.timestamp.isoformat(),
        "category": record.category.value,
        "value": record.value,
        "severity": record.severity.value,
        "notes": record.notes,
    }


def _intervention_from_dict(raw: object) -> Intervention:
    if not isinstance(raw, dict):
        raise TypeError("intervention record must be an object")
    return Intervention(
        timestamp=_parse_timestamp(raw["timestamp"]),
        type=InterventionType(raw["type"]),
        duration_minutes=_optional_int(raw.get("duration_minutes")),
        notes=_optional_str(raw.get("notes")),
    )


def _intervention_to_dict(record: Intervention) -> dict:
    return {
        "timestamp": record.timestamp.isoformat(),
        "type": record.type.value,
        "duration_minutes": record.duration_minutes,
        "notes": record.notes,
    }


def _temperature_from_dict(raw: object) -> NumericValue:
    if not isinstance(raw, dict):
        raise TypeError("temperature sample must be an object")
    value = _optional_float(raw.get("value"))
    if value is None:
        raise ValueError("temperature sample requires a value")
    timestamp = _parse_timestamp(raw["timestamp"])
    return NumericValue(
        value=value,
        unit=_optional_str(raw.get("unit")),
        provenance=Provenance.MEASURED,
        timestamp=timestamp,
    )


def _temperature_to_dict(sample: NumericValue) -> dict:
    return {
        "timestamp": (
            sample.timestamp.isoformat() if sample.timestamp is not None else None
        ),
        "value": sample.value,
        "unit": sample.unit,
    }


def _cycle_from_dict(raw: object) -> Cycle:
    if not isinstance(raw, dict):
        raise TypeError("cycle record must be an object")
    completed_at = raw.get("completed_at")
    output = raw.get("output")
    return Cycle(
        id=str(raw["id"]),
        started_at=_parse_timestamp(raw["started_at"]),
        status=CycleStatus(raw["status"]),
        completed_at=(
            _parse_timestamp(completed_at) if completed_at is not None else None
        ),
        output=_output_from_dict(output) if output is not None else None,
    )


def _cycle_to_dict(cycle: Cycle) -> dict:
    return {
        "id": cycle.id,
        "started_at": cycle.started_at.isoformat(),
        "status": cycle.status.value,
        "completed_at": (
            cycle.completed_at.isoformat()
            if cycle.completed_at is not None
            else None
        ),
        "output": (
            _output_to_dict(cycle.output) if cycle.output is not None else None
        ),
    }


def _output_from_dict(raw: object) -> Output:
    if not isinstance(raw, dict):
        raise TypeError("cycle output must be an object")
    quantity = raw.get("quantity_value")
    return Output(
        timestamp=_parse_timestamp(raw["timestamp"]),
        quantity_value=_optional_float(quantity) if quantity is not None else None,
        quantity_unit=_optional_str(raw.get("quantity_unit")),
        destination=_optional_str(raw.get("destination")),
        notes=_optional_str(raw.get("notes")),
    )


def _output_to_dict(output: Output) -> dict:
    return {
        "timestamp": output.timestamp.isoformat(),
        "quantity_value": output.quantity_value,
        "quantity_unit": output.quantity_unit,
        "destination": output.destination,
        "notes": output.notes,
    }


def _event_from_dict(raw: object) -> CompostEvent:
    if not isinstance(raw, dict):
        raise TypeError("event record must be an object")
    return CompostEvent(
        timestamp=_parse_timestamp(raw["timestamp"]),
        type=EventType(raw["type"]),
        origin=EventOrigin(raw["origin"]),
        bin_id=_optional_str(raw.get("bin_id")),
        cycle_id=_optional_str(raw.get("cycle_id")),
        before_state=_optional_str(raw.get("before_state")),
        after_state=_optional_str(raw.get("after_state")),
        reason=_optional_str(raw.get("reason")),
        notes=_optional_str(raw.get("notes")),
    )


def _event_to_dict(event: CompostEvent) -> dict:
    return {
        "timestamp": event.timestamp.isoformat(),
        "type": event.type.value,
        "origin": event.origin.value,
        "bin_id": event.bin_id,
        "cycle_id": event.cycle_id,
        "before_state": event.before_state,
        "after_state": event.after_state,
        "reason": event.reason,
        "notes": event.notes,
    }


def _state_from_dict(raw: object) -> CategoryState:
    if not isinstance(raw, dict):
        raise TypeError("notification state must be an object")
    since = raw.get("since")
    last_sent = raw.get("last_sent")
    return CategoryState(
        since=_parse_timestamp(since) if since is not None else None,
        notified=bool(raw.get("notified", False)),
        last_sent=_parse_timestamp(last_sent) if last_sent is not None else None,
    )


def _state_to_dict(state: CategoryState) -> dict:
    return {
        "since": state.since.isoformat() if state.since is not None else None,
        "notified": state.notified,
        "last_sent": (
            state.last_sent.isoformat() if state.last_sent is not None else None
        ),
    }


def _notification_states_from_raw(
    raw: object,
) -> tuple[tuple[str, CategoryState], ...]:
    """Parse the per-category engine memory; bad entries are skipped."""
    if raw is None:
        return ()
    if not isinstance(raw, dict):
        _LOGGER.warning("Stored notification states have unexpected shape; ignoring")
        return ()

    pairs: list[tuple[str, CategoryState]] = []
    for key, value in raw.items():
        try:
            category = NotificationCategory(str(key))
            state = _state_from_dict(value)
        except (TypeError, ValueError):
            _LOGGER.warning(
                "Skipping invalid stored notification state %r", key, exc_info=True
            )
            continue
        pairs.append((category.value, state))
    return tuple(sorted(pairs))
