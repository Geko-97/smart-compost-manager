"""Entity tests: unknown preserved, triade distinct, no duplicate sensors."""

from __future__ import annotations

from homeassistant.const import CONF_NAME, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.smart_compost.const import DOMAIN


def _make_entry(name: str, bin_id: str) -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title=name,
        unique_id=bin_id,
        version=1,
        data={
            "bin_id": bin_id,
            CONF_NAME: name,
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


async def test_zero_sensor_setup_creates_only_derived_entities(
    hass: HomeAssistant,
) -> None:
    entry = _make_entry("Garden Compost", "bin_garden")
    await _setup(hass, entry)

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

    # No physical measurement is ever duplicated (docs/05, docs/13).
    assert hass.states.get("sensor.garden_compost_temperature") is None
    assert hass.states.get("sensor.garden_compost_humidity") is None
    assert hass.states.get("sensor.garden_compost_moisture") is None


async def test_unknown_is_preserved_and_triade_is_distinct(
    hass: HomeAssistant,
) -> None:
    entry = _make_entry("Garden Compost", "bin_garden")
    await _setup(hass, entry)

    health = hass.states.get("sensor.garden_compost_health")
    data_quality = hass.states.get("sensor.garden_compost_data_quality")
    confidence = hass.states.get("sensor.garden_compost_confidence")
    assert health is not None
    assert data_quality is not None
    assert confidence is not None

    # Health with zero inputs is UNKNOWN, never a fabricated 0 (docs/06).
    assert health.state == STATE_UNKNOWN
    assert health.attributes["provenance"] == "unknown"

    assert data_quality.state == "0"
    # Hand-computed: 100 * 0.5 * (1 evidence / 3) = 16.67 → 17.
    assert confidence.state == "17"

    # The triade must read as three different numbers, never as one score.
    assert len({health.state, data_quality.state, confidence.state}) == 3

    # None of the derived entities is unavailable: unknown ≠ broken.
    for entity_id in (
        "sensor.garden_compost_health",
        "sensor.garden_compost_data_quality",
        "sensor.garden_compost_confidence",
        "sensor.garden_compost_priority_action",
        "sensor.garden_compost_cycle_stage",
        "sensor.garden_compost_phase",
        "sensor.garden_compost_cycle_report",
        "sensor.garden_compost_maturity",
    ):
        state = hass.states.get(entity_id)
        assert state is not None
        assert state.state != STATE_UNAVAILABLE


async def test_priority_action_and_cycle_stage(hass: HomeAssistant) -> None:
    entry = _make_entry("Garden Compost", "bin_garden")
    await _setup(hass, entry)

    action = hass.states.get("sensor.garden_compost_priority_action")
    assert action is not None
    assert action.state == "log_first_addition"
    assert action.attributes["severity"] == "suggestion"
    assert action.attributes["reason_code"] == "no_materials_logged"
    assert action.attributes["confidence"] == 17

    stage = hass.states.get("sensor.garden_compost_cycle_stage")
    assert stage is not None
    assert stage.state == "new"
    assert stage.attributes["options"] == [
        "new",
        "active",
        "resting",
        "completed",
    ]

    # Without a temperature history the phase stays UNKNOWN (docs/07).
    phase = hass.states.get("sensor.garden_compost_phase")
    assert phase is not None
    assert phase.state == STATE_UNKNOWN
    assert phase.attributes["provenance"] == "unknown"
    assert phase.attributes["confidence"] == 0
    assert "no_temperature_history" in phase.attributes["limitations"]
    assert phase.attributes["sample_count"] == 0

    # No cycle was ever started: the report is UNKNOWN, never a fake 0.
    report = hass.states.get("sensor.garden_compost_cycle_report")
    assert report is not None
    assert report.state == STATE_UNKNOWN

    # No material logged: maturity cannot be declared (docs/07 §9).
    maturity = hass.states.get("sensor.garden_compost_maturity")
    assert maturity is not None
    assert maturity.state == STATE_UNKNOWN
    assert maturity.attributes["provenance"] == "unknown"
    assert maturity.attributes["confidence"] == 0
    assert maturity.attributes["limitations"] == ["no_material_logged"]
    assert maturity.attributes["forecast"] is None
    assert maturity.attributes["options"] == [
        "ready_for_curing",
        "likely_mature",
        "likely_suitable_for_garden_use",
    ]


async def test_bin_becomes_one_device(hass: HomeAssistant) -> None:
    entry = _make_entry("Garden Compost", "bin_garden")
    await _setup(hass, entry)

    registry = dr.async_get(hass)
    device = registry.async_get_device_by_identifier(
        (DOMAIN, "bin_garden"), entry.entry_id
    )
    assert device is not None
    assert device.name == "Garden Compost"
    assert device.model == "enclosed_bin"
    linked = er.async_entries_for_device(er.async_get(hass), device.id)
    assert len(linked) == 8


async def test_two_bins_are_isolated(hass: HomeAssistant) -> None:
    entry_a = _make_entry("Alpha Compost", "bin_alpha")
    entry_b = _make_entry("Beta Compost", "bin_beta")
    await _setup(hass, entry_a)
    await _setup(hass, entry_b)

    registry = dr.async_get(hass)
    device_a = registry.async_get_device_by_identifier(
        (DOMAIN, "bin_alpha"), entry_a.entry_id
    )
    device_b = registry.async_get_device_by_identifier(
        (DOMAIN, "bin_beta"), entry_b.entry_id
    )
    assert device_a is not None and device_b is not None
    assert device_a.id != device_b.id

    entity_registry = er.async_get(hass)
    ids_a = {
        item.unique_id
        for item in er.async_entries_for_config_entry(
            entity_registry, entry_a.entry_id
        )
    }
    ids_b = {
        item.unique_id
        for item in er.async_entries_for_config_entry(
            entity_registry, entry_b.entry_id
        )
    }
    assert ids_a.isdisjoint(ids_b)

    health_a = hass.states.get("sensor.alpha_compost_health")
    health_b = hass.states.get("sensor.beta_compost_health")
    assert health_a is not None and health_b is not None
    assert health_a.state == STATE_UNKNOWN
    assert health_b.state == STATE_UNKNOWN
