"""Binding of EXISTING Home Assistant sensors as read-only inputs.

The integration never creates physical sensor entities (docs/05, docs/13):
it only reads entities the user already has, and only while they are fresh.
Anything unavailable, non-numeric or stale maps to "no measurement", which
drops the capability so downstream domains fall back to UNKNOWN.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from datetime import datetime
from enum import StrEnum
from typing import Any

from homeassistant.const import (
    ATTR_UNIT_OF_MEASUREMENT,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import State

from .const import (
    CONF_AMMONIA_ENTITY,
    CONF_FILL_ENTITY,
    CONF_MOISTURE_ENTITY,
    CONF_TEMPERATURE_ENTITY,
    CONF_VOC_ENTITY,
)
from .core.constants import SENSOR_STALE_AFTER
from .core.model import Capability, NumericValue, Provenance


class InputKind(StrEnum):
    """Which bin input a bound entity feeds (HA-side wiring only, M9).

    Two entities may share one capability (VOC and ammonia both are gas
    signals): the kind keeps them apart so a stale VOC sensor can never
    silently turn into an ammonia reading.
    """

    TEMPERATURE = "temperature"
    MOISTURE = "moisture"
    VOC = "voc"
    AMMONIA = "ammonia"
    FILL = "fill"

    @property
    def capability(self) -> Capability:
        """The capability ladder step this input unlocks (docs/04)."""
        return _KIND_CAPABILITY[self]


_KIND_CAPABILITY: dict[InputKind, Capability] = {
    InputKind.TEMPERATURE: Capability.INTERNAL_TEMPERATURE,
    InputKind.MOISTURE: Capability.INTERNAL_MOISTURE,
    InputKind.VOC: Capability.GAS_SIGNALS,
    InputKind.AMMONIA: Capability.GAS_SIGNALS,
    InputKind.FILL: Capability.WEIGHT_FILL,
}

#: Options key → which input it feeds.
_KIND_OPTIONS: tuple[tuple[InputKind, str], ...] = (
    (InputKind.TEMPERATURE, CONF_TEMPERATURE_ENTITY),
    (InputKind.MOISTURE, CONF_MOISTURE_ENTITY),
    (InputKind.VOC, CONF_VOC_ENTITY),
    (InputKind.AMMONIA, CONF_AMMONIA_ENTITY),
    (InputKind.FILL, CONF_FILL_ENTITY),
)


def measurement_from_state(
    state: State | None, now: datetime
) -> NumericValue | None:
    """Read a bound sensor state; unusable input maps to None (not to 0)."""
    if state is None or state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
        return None
    try:
        raw = float(state.state)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(raw):
        return None
    updated = state.last_updated
    if updated is None or (now - updated) > SENSOR_STALE_AFTER:
        return None
    return NumericValue(
        value=raw,
        unit=state.attributes.get(ATTR_UNIT_OF_MEASUREMENT),
        provenance=Provenance.MEASURED,
        timestamp=updated,
    )


def read_bindings(options: Mapping[str, Any]) -> dict[str, InputKind]:
    """Map bound entity ids (options flow output) to the input they feed."""
    bindings: dict[str, InputKind] = {}
    for kind, key in _KIND_OPTIONS:
        entity_id = _first_entity(options, key)
        if entity_id:
            bindings[entity_id] = kind
    return bindings


def _first_entity(options: Mapping[str, Any], key: str) -> str | None:
    value = options.get(key)
    if isinstance(value, str) and value:
        return value
    if isinstance(value, list) and value and isinstance(value[0], str):
        return value[0]
    return None
