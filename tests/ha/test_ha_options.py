"""Options flow tests: sensor binding is read-only, reactive and clearable."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import (
    ATTR_UNIT_OF_MEASUREMENT,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.smart_compost.const import DOMAIN

TEMPERATURE_ENTITY = "sensor.compost_internal_temp"


def _make_entry(name: str, bin_id: str) -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title=name,
        unique_id=bin_id,
        version=1,
        data={
            "bin_id": bin_id,
            "name": name,
            "compost_type": "enclosed_bin",
            "method": "continuous",
            "location": "outdoor",
            "shelter": "unknown",
            "rain_exposure": "unknown",
            "sun_exposure": "unknown",
        },
    )


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def _configure_options(
    hass: HomeAssistant, entry: MockConfigEntry, user_input: dict[str, Any]
):
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input
    )
    await hass.async_block_till_done()
    return result


def _set_temperature(hass: HomeAssistant, value: str) -> None:
    hass.states.async_set(
        TEMPERATURE_ENTITY,
        value,
        {
            ATTR_UNIT_OF_MEASUREMENT: "°C",
            "device_class": "temperature",
            "state_class": "measurement",
        },
    )


async def test_binding_a_sensor_drives_health_and_stays_reactive(
    hass: HomeAssistant,
) -> None:
    entry = _make_entry("Garden Compost", "bin_garden")
    await _setup(hass, entry)

    # Zero sensors: unknown health, no data.
    health = hass.states.get("sensor.garden_compost_health")
    assert health is not None and health.state == STATE_UNKNOWN

    _set_temperature(hass, "50")
    result = await _configure_options(
        hass,
        entry,
        {
            "temperature_entity": [TEMPERATURE_ENTITY],
            "moisture_entity": [],
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options["temperature_entity"] == [TEMPERATURE_ENTITY]
    # The update listener reloaded the entry with the new binding.
    assert entry.state is ConfigEntryState.LOADED

    health = hass.states.get("sensor.garden_compost_health")
    data_quality = hass.states.get("sensor.garden_compost_data_quality")
    confidence = hass.states.get("sensor.garden_compost_confidence")
    action = hass.states.get("sensor.garden_compost_priority_action")
    assert health is not None and health.state == "90"
    assert health.attributes["provenance"] == "inferred"
    assert health.attributes["evaluable_domains"] == ["thermal"]
    # DQ: 100 * (0.5 * 1/2) = 25; confidence: 100 * (0.5 * 1/6 + 0.5 * 2/3).
    assert data_quality is not None and data_quality.state == "25"
    assert confidence is not None and confidence.state == "42"
    # No materials logged yet: onboarding prompt still wins for 90 °C.
    assert action is not None and action.state == "log_first_addition"

    # Event-driven: no polling, the new sensor state re-assesses the bin.
    _set_temperature(hass, "80")
    await hass.async_block_till_done()
    health = hass.states.get("sensor.garden_compost_health")
    assert health is not None and health.state == "45"

    # Unavailable sensor: capability drops, nothing stale is consumed.
    hass.states.async_set(TEMPERATURE_ENTITY, STATE_UNAVAILABLE)
    await hass.async_block_till_done()
    health = hass.states.get("sensor.garden_compost_health")
    data_quality = hass.states.get("sensor.garden_compost_data_quality")
    assert health is not None and health.state == STATE_UNKNOWN
    assert data_quality is not None and data_quality.state == "0"


async def test_binding_creates_no_duplicate_physical_sensors(
    hass: HomeAssistant,
) -> None:
    entry = _make_entry("Garden Compost", "bin_garden")
    await _setup(hass, entry)
    _set_temperature(hass, "50")
    await _configure_options(
        hass, entry, {"temperature_entity": [TEMPERATURE_ENTITY], "moisture_entity": []}
    )

    registry = er.async_get(hass)
    entries = er.async_entries_for_config_entry(registry, entry.entry_id)
    assert {item.unique_id for item in entries} == {
        "bin_garden_health",
        "bin_garden_data_quality",
        "bin_garden_confidence",
        "bin_garden_priority_action",
        "bin_garden_cycle_stage",
        "bin_garden_phase",
        "bin_garden_cycle_report",
        "bin_garden_maturity",
    }
    # The bound entity is only read, never copied.
    assert hass.states.get("sensor.garden_compost_temperature") is None


async def test_clearing_the_binding_returns_to_unknown(
    hass: HomeAssistant,
) -> None:
    entry = _make_entry("Garden Compost", "bin_garden")
    await _setup(hass, entry)
    _set_temperature(hass, "50")
    await _configure_options(
        hass, entry, {"temperature_entity": [TEMPERATURE_ENTITY], "moisture_entity": []}
    )
    health = hass.states.get("sensor.garden_compost_health")
    assert health is not None and health.state == "90"

    result = await _configure_options(
        hass, entry, {"temperature_entity": [], "moisture_entity": []}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options["temperature_entity"] == []
    health = hass.states.get("sensor.garden_compost_health")
    assert health is not None and health.state == STATE_UNKNOWN


async def test_same_sensor_for_both_bindings_is_rejected(
    hass: HomeAssistant,
) -> None:
    entry = _make_entry("Garden Compost", "bin_garden")
    await _setup(hass, entry)
    _set_temperature(hass, "50")

    result = await _configure_options(
        hass,
        entry,
        {
            "temperature_entity": [TEMPERATURE_ENTITY],
            "moisture_entity": [TEMPERATURE_ENTITY],
        },
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "same_sensor"}
    # Nothing was written.
    assert entry.options == {}
