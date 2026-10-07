"""Service actions: log materials, observations, interventions and cycles.

Registered in `async_setup` (once, even with zero bins) per HA guidance, and
targeted at the **device** level: the device *is* the bin, so the action
always states explicitly which bin it writes to (docs/16).
"""

from __future__ import annotations

from datetime import UTC, datetime

import voluptuous as vol
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr

from .const import DOMAIN
from .coordinator import BinRuntime
from .core.model import (
    Intervention,
    InterventionType,
    MaterialAddition,
    ObservationCategory,
    Output,
    QuantityPrecision,
    UserObservation,
)

SERVICE_LOG_MATERIAL = "log_material"
SERVICE_LOG_OBSERVATION = "log_observation"
SERVICE_LOG_INTERVENTION = "log_intervention"
SERVICE_START_CYCLE = "start_cycle"
SERVICE_COMPLETE_CYCLE = "complete_cycle"

CONF_MATERIAL_TYPE = "material_type"
CONF_QUANTITY = "quantity"
CONF_QUANTITY_UNIT = "quantity_unit"
CONF_QUANTITY_PRECISION = "quantity_precision"
CONF_NOTES = "notes"
CONF_CATEGORY = "category"
CONF_VALUE = "value"
CONF_TYPE = "type"
CONF_DURATION_MINUTES = "duration_minutes"
CONF_OUTPUT_QUANTITY = "output_quantity"
CONF_OUTPUT_UNIT = "output_unit"
CONF_OUTPUT_DESTINATION = "output_destination"
CONF_OUTPUT_NOTES = "output_notes"

DEVICE_FIELD = {vol.Required(CONF_DEVICE_ID): str}

LOG_MATERIAL_SCHEMA = vol.Schema(
    {
        **DEVICE_FIELD,
        vol.Required(CONF_MATERIAL_TYPE): str,
        vol.Optional(CONF_QUANTITY): vol.All(
            vol.Coerce(float), vol.Range(min=0)
        ),
        vol.Optional(CONF_QUANTITY_UNIT): str,
        vol.Optional(CONF_QUANTITY_PRECISION): vol.In(
            [member.value for member in QuantityPrecision]
        ),
        vol.Optional(CONF_NOTES): str,
    },
    extra=vol.PREVENT_EXTRA,
)

LOG_OBSERVATION_SCHEMA = vol.Schema(
    {
        **DEVICE_FIELD,
        vol.Required(CONF_CATEGORY): vol.In(
            [member.value for member in ObservationCategory]
        ),
        vol.Required(CONF_VALUE): str,
        vol.Optional(CONF_NOTES): str,
    },
    extra=vol.PREVENT_EXTRA,
)

LOG_INTERVENTION_SCHEMA = vol.Schema(
    {
        **DEVICE_FIELD,
        vol.Required(CONF_TYPE): vol.In(
            [member.value for member in InterventionType]
        ),
        vol.Optional(CONF_DURATION_MINUTES): vol.All(
            vol.Coerce(int), vol.Range(min=0)
        ),
        vol.Optional(CONF_NOTES): str,
    },
    extra=vol.PREVENT_EXTRA,
)

START_CYCLE_SCHEMA = vol.Schema(
    {
        **DEVICE_FIELD,
        vol.Optional(CONF_NOTES): str,
    },
    extra=vol.PREVENT_EXTRA,
)

COMPLETE_CYCLE_SCHEMA = vol.Schema(
    {
        **DEVICE_FIELD,
        vol.Optional(CONF_OUTPUT_QUANTITY): vol.All(
            vol.Coerce(float), vol.Range(min=0)
        ),
        vol.Optional(CONF_OUTPUT_UNIT): str,
        vol.Optional(CONF_OUTPUT_DESTINATION): str,
        vol.Optional(CONF_OUTPUT_NOTES): str,
    },
    extra=vol.PREVENT_EXTRA,
)


def _runtime_for_device(hass: HomeAssistant, device_id: str) -> BinRuntime:
    """Resolve the targeted device to a loaded compost bin.

    Errors are explicit: an unknown or unloaded device must never fall back
    to some other bin (docs/11: cross-bin writes are impossible).
    """
    device = dr.async_get(hass).async_get(device_id)
    if device is not None:
        for entry_id in device.config_entries:
            entry = hass.config_entries.async_get_entry(entry_id)
            if entry is None or entry.domain != DOMAIN:
                continue
            if entry.state is not ConfigEntryState.LOADED:
                raise ServiceValidationError(
                    translation_domain=DOMAIN,
                    translation_key="bin_not_loaded",
                    translation_placeholders={"device_id": device_id},
                )
            return entry.runtime_data

    raise ServiceValidationError(
        translation_domain=DOMAIN,
        translation_key="bin_not_found",
        translation_placeholders={"device_id": device_id},
    )


def async_register_services(hass: HomeAssistant) -> None:
    """Register all service actions of the integration (idempotent)."""

    async def _handle_log_material(call: ServiceCall) -> None:
        runtime = _runtime_for_device(hass, call.data[CONF_DEVICE_ID])
        quantity = call.data.get(CONF_QUANTITY)
        precision = call.data.get(CONF_QUANTITY_PRECISION)
        if precision is None:
            # Honest default: a number without stated precision is
            # approximate; no number at all is a qualitative report.
            precision = (
                QuantityPrecision.APPROXIMATE.value
                if quantity is not None
                else QuantityPrecision.QUALITATIVE.value
            )
        await runtime.coordinator.async_log_material(
            MaterialAddition(
                timestamp=datetime.now(UTC),
                material_type=call.data[CONF_MATERIAL_TYPE],
                quantity_value=quantity,
                quantity_unit=call.data.get(CONF_QUANTITY_UNIT),
                quantity_precision=QuantityPrecision(precision),
                notes=call.data.get(CONF_NOTES),
            )
        )

    async def _handle_log_observation(call: ServiceCall) -> None:
        runtime = _runtime_for_device(hass, call.data[CONF_DEVICE_ID])
        await runtime.coordinator.async_log_observation(
            UserObservation(
                timestamp=datetime.now(UTC),
                category=ObservationCategory(call.data[CONF_CATEGORY]),
                value=call.data[CONF_VALUE],
                notes=call.data.get(CONF_NOTES),
            )
        )

    async def _handle_log_intervention(call: ServiceCall) -> None:
        runtime = _runtime_for_device(hass, call.data[CONF_DEVICE_ID])
        await runtime.coordinator.async_log_intervention(
            Intervention(
                timestamp=datetime.now(UTC),
                type=InterventionType(call.data[CONF_TYPE]),
                duration_minutes=call.data.get(CONF_DURATION_MINUTES),
                notes=call.data.get(CONF_NOTES),
            )
        )

    hass.services.async_register(
        DOMAIN,
        SERVICE_LOG_MATERIAL,
        _handle_log_material,
        schema=LOG_MATERIAL_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_LOG_OBSERVATION,
        _handle_log_observation,
        schema=LOG_OBSERVATION_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_LOG_INTERVENTION,
        _handle_log_intervention,
        schema=LOG_INTERVENTION_SCHEMA,
    )

    async def _handle_start_cycle(call: ServiceCall) -> None:
        runtime = _runtime_for_device(hass, call.data[CONF_DEVICE_ID])
        await runtime.coordinator.async_start_cycle(
            notes=call.data.get(CONF_NOTES)
        )

    async def _handle_complete_cycle(call: ServiceCall) -> None:
        runtime = _runtime_for_device(hass, call.data[CONF_DEVICE_ID])
        quantity = call.data.get(CONF_OUTPUT_QUANTITY)
        unit = call.data.get(CONF_OUTPUT_UNIT)
        destination = call.data.get(CONF_OUTPUT_DESTINATION)
        notes = call.data.get(CONF_OUTPUT_NOTES)
        # No field at all means "no output report": an unmeasured output
        # stays None, never a fabricated 0 (docs/04).
        output = None
        if (
            quantity is not None
            or unit is not None
            or destination is not None
            or notes is not None
        ):
            output = Output(
                timestamp=datetime.now(UTC),
                quantity_value=quantity,
                quantity_unit=unit,
                destination=destination,
                notes=notes,
            )
        await runtime.coordinator.async_complete_cycle(output)

    hass.services.async_register(
        DOMAIN,
        SERVICE_START_CYCLE,
        _handle_start_cycle,
        schema=START_CYCLE_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_COMPLETE_CYCLE,
        _handle_complete_cycle,
        schema=COMPLETE_CYCLE_SCHEMA,
    )
