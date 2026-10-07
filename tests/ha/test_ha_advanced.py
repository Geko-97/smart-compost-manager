"""End-to-end M9: advanced signal bindings (docs/13 §3, docs/14 §7, docs/05).

The options flow reads VOC, ammonia and fill sensors exactly like
temperature and moisture: read-only, fresh-only, unit-checked. A reading
never claims alone — the diagnostic only appears when a second signal
corroborates it, and it disappears the moment either signal does.
"""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import (
    ATTR_UNIT_OF_MEASUREMENT,
    CONF_DEVICE_ID,
    STATE_UNAVAILABLE,
)
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.smart_compost.const import DOMAIN

TEMPERATURE_ENTITY = "sensor.compost_internal_temp"
MOISTURE_ENTITY = "sensor.compost_internal_moisture"
VOC_ENTITY = "sensor.compost_voc"
AMMONIA_ENTITY = "sensor.compost_ammonia"
FILL_ENTITY = "sensor.compost_fill"

HEALTH_SENSOR = "sensor.garden_compost_health"


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
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input
    )
    await hass.async_block_till_done()
    return result


def _set(hass: HomeAssistant, entity_id: str, value: str, unit: str) -> None:
    hass.states.async_set(
        entity_id,
        value,
        {ATTR_UNIT_OF_MEASUREMENT: unit, "state_class": "measurement"},
    )


def _diagnostics(hass: HomeAssistant) -> list[dict[str, Any]]:
    health = hass.states.get(HEALTH_SENSOR)
    assert health is not None
    return list(health.attributes["diagnostics"])


async def _log_material(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    device = dr.async_get(hass).async_get_device_by_identifier(
        (DOMAIN, entry.unique_id), entry.entry_id
    )
    assert device is not None
    await hass.services.async_call(
        DOMAIN,
        "log_material",
        {CONF_DEVICE_ID: device.id, "material_type": "food_scraps"},
        blocking=True,
    )
    await hass.async_block_till_done()


async def test_voc_binding_drives_the_diagnostic_and_stays_reactive(
    hass: HomeAssistant,
) -> None:
    entry = _make_entry("Garden Compost", "bin_garden")
    await _setup(hass, entry)

    _set(hass, MOISTURE_ENTITY, "75", "%")
    _set(hass, VOC_ENTITY, "1500", "ppb")

    # One signal (wet moisture) is not a finding yet.
    result = await _configure_options(
        hass,
        entry,
        {
            "temperature_entity": [],
            "moisture_entity": [MOISTURE_ENTITY],
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert _diagnostics(hass) == []

    # The VOC binding adds the second signal: the finding appears.
    result = await _configure_options(
        hass,
        entry,
        {
            "temperature_entity": [],
            "moisture_entity": [MOISTURE_ENTITY],
            "voc_entity": [VOC_ENTITY],
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.state is ConfigEntryState.LOADED
    assert _diagnostics(hass) == [
        {
            "code": "possible_anaerobic_activity",
            "confidence": 70,
            "signals": ["elevated_voc", "internal_moisture_too_wet"],
        }
    ]

    # Event-driven: a normal VOC reading re-assesses the bin at once.
    _set(hass, VOC_ENTITY, "400", "ppb")
    await hass.async_block_till_done()
    assert _diagnostics(hass) == []

    _set(hass, VOC_ENTITY, "1500", "ppb")
    await hass.async_block_till_done()
    assert [item["code"] for item in _diagnostics(hass)] == [
        "possible_anaerobic_activity"
    ]

    # An unavailable VOC sensor drops its capability: no stale claim.
    hass.states.async_set(VOC_ENTITY, STATE_UNAVAILABLE)
    await hass.async_block_till_done()
    assert _diagnostics(hass) == []

    # Clearing the bindings returns to unknown (docs/04).
    result = await _configure_options(
        hass,
        entry,
        {"temperature_entity": [], "moisture_entity": [], "voc_entity": []},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options["voc_entity"] == []
    health = hass.states.get(HEALTH_SENSOR)
    assert health is not None and health.state == "unknown"


async def test_fill_binding_reports_a_full_bin_that_is_still_fed(
    hass: HomeAssistant,
) -> None:
    entry = _make_entry("Garden Compost", "bin_garden")
    await _setup(hass, entry)

    _set(hass, FILL_ENTITY, "90", "%")
    result = await _configure_options(
        hass,
        entry,
        {
            "temperature_entity": [],
            "moisture_entity": [],
            "fill_entity": [FILL_ENTITY],
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    # A high fill level alone is an observation, not a diagnosis.
    assert _diagnostics(hass) == []

    await _log_material(hass, entry)

    assert _diagnostics(hass) == [
        {
            "code": "bin_nearly_full",
            "confidence": 70,
            "signals": ["fill_level_high", "recent_fueling"],
        }
    ]


async def test_ammonia_binding_needs_a_green_heavy_balance(
    hass: HomeAssistant,
) -> None:
    entry = _make_entry("Garden Compost", "bin_garden")
    await _setup(hass, entry)

    _set(hass, AMMONIA_ENTITY, "6000", "ppb")
    result = await _configure_options(
        hass,
        entry,
        {
            "temperature_entity": [],
            "moisture_entity": [],
            "ammonia_entity": [AMMONIA_ENTITY],
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    # Elevated ammonia on its own claims nothing.
    assert _diagnostics(hass) == []


async def test_the_same_sensor_cannot_feed_two_inputs(
    hass: HomeAssistant,
) -> None:
    entry = _make_entry("Garden Compost", "bin_garden")
    await _setup(hass, entry)
    _set(hass, TEMPERATURE_ENTITY, "45", "°C")

    result = await _configure_options(
        hass,
        entry,
        {
            "temperature_entity": [TEMPERATURE_ENTITY],
            "moisture_entity": [],
            "voc_entity": [TEMPERATURE_ENTITY],
        },
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "same_sensor"}
    assert entry.options == {}
