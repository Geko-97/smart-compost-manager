"""Service action tests: logging updates the assessment, history persists."""

from __future__ import annotations

from typing import Any

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_DEVICE_ID
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.service import async_get_all_descriptions
from homeassistant.helpers.translation import async_get_translations
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.smart_compost.const import DOMAIN

EXPECTED_FIELDS = {
    "log_material": {
        "device_id",
        "material_type",
        "quantity",
        "quantity_unit",
        "quantity_precision",
        "notes",
    },
    "log_observation": {"device_id", "category", "value", "notes"},
    "log_intervention": {"device_id", "type", "duration_minutes", "notes"},
    "start_cycle": {"device_id", "notes"},
    "complete_cycle": {
        "device_id",
        "output_quantity",
        "output_unit",
        "output_destination",
        "output_notes",
    },
}


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


def _device_id(hass: HomeAssistant, entry: MockConfigEntry) -> str:
    device = dr.async_get(hass).async_get_device_by_identifier(
        (DOMAIN, entry.data["bin_id"]), entry.entry_id
    )
    assert device is not None
    return device.id


def _store_key(entry: MockConfigEntry) -> str:
    return f"{DOMAIN}.{entry.entry_id}"


def _stored(hass_storage: dict[str, Any], entry: MockConfigEntry) -> dict:
    """Persisted history of a bin, as seen through the (mocked) HA storage."""
    key = _store_key(entry)
    assert key in hass_storage, f"store key missing: {key}"
    return hass_storage[key]["data"]


async def test_services_are_registered_even_without_bins(hass: HomeAssistant) -> None:
    assert await async_setup_component(hass, DOMAIN, {})
    for service in EXPECTED_FIELDS:
        assert hass.services.has_service(DOMAIN, service)


async def test_registered_services_are_translated(hass: HomeAssistant) -> None:
    entry = _make_entry("Garden Compost", "bin_garden")
    await _setup(hass, entry)

    # Fields come from services.yaml...
    descriptions = await async_get_all_descriptions(hass)
    services = descriptions[DOMAIN]
    for name, expected_fields in EXPECTED_FIELDS.items():
        assert set(services[name]["fields"]) == expected_fields

    # ...names and descriptions come from the translation files.
    translations = await async_get_translations(
        hass, "en", "services", integrations=[DOMAIN]
    )

    def translated(suffix: str) -> str:
        matches = [
            value
            for key, value in translations.items()
            if key.endswith(suffix)
        ]
        assert matches, f"missing translation: *.{suffix}"
        return matches[0]

    assert translated("services.log_material.name") == "Log material addition"
    assert translated("services.log_observation.name") == "Log observation"
    assert translated("services.log_intervention.name") == "Log intervention"
    assert translated("services.start_cycle.name") == "Start cycle"
    assert translated("services.complete_cycle.name") == "Complete cycle"

    for name, expected_fields in EXPECTED_FIELDS.items():
        assert translated(f"services.{name}.description")
        for field in expected_fields:
            assert translated(f"services.{name}.fields.{field}.name")
            assert translated(f"services.{name}.fields.{field}.description")


async def test_log_material_updates_the_assessment(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    entry = _make_entry("Garden Compost", "bin_garden")
    await _setup(hass, entry)
    device_id = _device_id(hass, entry)

    await hass.services.async_call(
        DOMAIN,
        "log_material",
        {
            CONF_DEVICE_ID: device_id,
            "material_type": "food_scraps",
            "quantity": 2,
            "quantity_unit": "bucket",
        },
        blocking=True,
    )
    await hass.async_block_till_done()

    stage = hass.states.get("sensor.garden_compost_cycle_stage")
    action = hass.states.get("sensor.garden_compost_priority_action")
    data_quality = hass.states.get("sensor.garden_compost_data_quality")
    confidence = hass.states.get("sensor.garden_compost_confidence")
    health = hass.states.get("sensor.garden_compost_health")
    assert stage is not None and stage.state == "active"
    assert action is not None and action.state == "none"
    # DQ: 100 * (0.3 * 0.5 material + 0.2 * fresh) = 35.
    assert data_quality is not None and data_quality.state == "35"
    assert confidence is not None and confidence.state == "17"
    # Manual data never fakes a health score.
    assert health is not None and health.state == "unknown"

    # A quantity without stated precision is stored as approximate, not exact.
    stored = _stored(hass_storage, entry)
    assert len(stored["materials"]) == 1
    material = stored["materials"][0]
    assert material["material_type"] == "food_scraps"
    assert material["quantity_value"] == 2.0
    assert material["quantity_precision"] == "approximate"


async def test_log_material_without_quantity_is_qualitative(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    entry = _make_entry("Garden Compost", "bin_garden")
    await _setup(hass, entry)

    await hass.services.async_call(
        DOMAIN,
        "log_material",
        {CONF_DEVICE_ID: _device_id(hass, entry), "material_type": "leaves"},
        blocking=True,
    )
    await hass.async_block_till_done()

    material = _stored(hass_storage, entry)["materials"][0]
    assert material["quantity_value"] is None
    assert material["quantity_unit"] is None
    assert material["quantity_precision"] == "qualitative"


async def test_data_quality_rises_with_each_fresh_input(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    entry = _make_entry("Garden Compost", "bin_garden")
    await _setup(hass, entry)
    device_id = _device_id(hass, entry)

    await hass.services.async_call(
        DOMAIN,
        "log_material",
        {CONF_DEVICE_ID: device_id, "material_type": "food_scraps"},
        blocking=True,
    )
    data_quality = hass.states.get("sensor.garden_compost_data_quality")
    assert data_quality is not None and data_quality.state == "35"

    await hass.services.async_call(
        DOMAIN,
        "log_observation",
        {
            CONF_DEVICE_ID: device_id,
            "category": "moisture",
            "value": "damp",
        },
        blocking=True,
    )
    # DQ: 100 * (0.3 * (0.5 + 0.3) + 0.2) = 44.
    data_quality = hass.states.get("sensor.garden_compost_data_quality")
    assert data_quality is not None and data_quality.state == "44"

    await hass.services.async_call(
        DOMAIN,
        "log_intervention",
        {CONF_DEVICE_ID: device_id, "type": "turning"},
        blocking=True,
    )
    # DQ: 100 * (0.3 * 1.0 + 0.2) = 50.
    data_quality = hass.states.get("sensor.garden_compost_data_quality")
    assert data_quality is not None and data_quality.state == "50"
    await hass.async_block_till_done()

    stored = _stored(hass_storage, entry)
    assert len(stored["observations"]) == 1
    assert len(stored["interventions"]) == 1


async def test_unknown_device_is_rejected(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    entry = _make_entry("Garden Compost", "bin_garden")
    await _setup(hass, entry)

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            "log_material",
            {CONF_DEVICE_ID: "not-a-device", "material_type": "food_scraps"},
            blocking=True,
        )

    # Nothing was written anywhere.
    assert _store_key(entry) not in hass_storage


async def test_history_survives_reload(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    entry = _make_entry("Garden Compost", "bin_garden")
    await _setup(hass, entry)

    await hass.services.async_call(
        DOMAIN,
        "log_material",
        {
            CONF_DEVICE_ID: _device_id(hass, entry),
            "material_type": "food_scraps",
        },
        blocking=True,
    )
    await hass.async_block_till_done()

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    stage = hass.states.get("sensor.garden_compost_cycle_stage")
    data_quality = hass.states.get("sensor.garden_compost_data_quality")
    action = hass.states.get("sensor.garden_compost_priority_action")
    assert stage is not None and stage.state == "active"
    assert data_quality is not None and data_quality.state == "35"
    assert action is not None and action.state == "none"


async def test_service_calls_stay_isolated_per_bin(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    entry_a = _make_entry("Alpha Compost", "bin_alpha")
    entry_b = _make_entry("Beta Compost", "bin_beta")
    await _setup(hass, entry_a)
    await _setup(hass, entry_b)

    await hass.services.async_call(
        DOMAIN,
        "log_material",
        {CONF_DEVICE_ID: _device_id(hass, entry_a), "material_type": "grass"},
        blocking=True,
    )
    await hass.async_block_till_done()

    stage_a = hass.states.get("sensor.alpha_compost_cycle_stage")
    stage_b = hass.states.get("sensor.beta_compost_cycle_stage")
    dq_a = hass.states.get("sensor.alpha_compost_data_quality")
    dq_b = hass.states.get("sensor.beta_compost_data_quality")

    assert stage_a is not None and stage_a.state == "active"
    assert dq_a is not None and dq_a.state == "35"
    # Bin B saw none of it: still new, still no data.
    assert stage_b is not None and stage_b.state == "new"
    assert dq_b is not None and dq_b.state == "0"

    assert len(_stored(hass_storage, entry_a)["materials"]) == 1
    assert _store_key(entry_b) not in hass_storage


async def test_health_becomes_actionable_from_logged_data(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    """M3 e2e: three greens → health 40 + add_browns; odor → aeration."""
    entry = _make_entry("Garden Compost", "bin_garden")
    await _setup(hass, entry)
    device_id = _device_id(hass, entry)

    for _ in range(3):
        await hass.services.async_call(
            DOMAIN,
            "log_material",
            {CONF_DEVICE_ID: device_id, "material_type": "food_scraps"},
            blocking=True,
        )
    await hass.async_block_till_done()

    health = hass.states.get("sensor.garden_compost_health")
    action = hass.states.get("sensor.garden_compost_priority_action")
    confidence = hass.states.get("sensor.garden_compost_confidence")
    assert health is not None and health.state == "40"
    assert health.attributes["provenance"] == "inferred"
    assert health.attributes["evaluable_domains"] == ["balance"]
    assert health.attributes["domain_scores"] == {
        "thermal": None,
        "moisture": None,
        "balance": 40,
        "aeration": None,
    }
    assert action is not None and action.state == "add_browns"
    assert action.attributes["reason_code"] == "greens_without_browns"
    # Confidence: 100 * (0.5 * 1/6 + 0.5 * 2/3) = 41.67 → 42.
    assert confidence is not None and confidence.state == "42"

    await hass.services.async_call(
        DOMAIN,
        "log_observation",
        {
            CONF_DEVICE_ID: device_id,
            "category": "odor",
            "value": "sour smell",
        },
        blocking=True,
    )
    await hass.async_block_till_done()

    health = hass.states.get("sensor.garden_compost_health")
    action = hass.states.get("sensor.garden_compost_priority_action")
    confidence = hass.states.get("sensor.garden_compost_confidence")
    # round((40 + 45) / 2) = 42; confidence: 100 * (0.5 * 2/6 + 0.5) = 67.
    assert health is not None and health.state == "42"
    assert health.attributes["evaluable_domains"] == ["balance", "aeration"]
    assert action is not None and action.state == "improve_aeration"
    assert confidence is not None and confidence.state == "67"
