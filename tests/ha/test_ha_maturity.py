"""End-to-end M8: maturity entity, forecast window and notification (docs/07).

Sequence coverage: nothing logged is UNKNOWN, a young batch stays UNKNOWN,
ten quiet days reach the weakest readiness with a forecast WINDOW (never a
date), the transition lands on the bus as `maturity_estimated` plus a
`maturity` notification, and a reload neither replays nor loses any of it
(PR-027).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from freezegun import freeze_time
from homeassistant.const import CONF_DEVICE_ID, STATE_UNKNOWN
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.smart_compost.const import (
    DOMAIN,
    EVENT_COMPOST_EVENT,
    EVENT_COMPOST_NOTIFICATION,
)

MATURITY_SENSOR = "sensor.garden_compost_maturity"


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
            "method": "batch",
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


def _listen(hass: HomeAssistant, signal: str) -> list[dict[str, Any]]:
    """Collect fired payloads in dispatch order (see test_ha_notifications)."""
    captured: list[dict[str, Any]] = []

    @callback
    def _record(event: Any) -> None:
        captured.append(event.data)

    hass.bus.async_listen(signal, _record)
    return captured


async def _call(
    hass: HomeAssistant, entry: MockConfigEntry, service: str, payload: dict
) -> None:
    await hass.services.async_call(
        DOMAIN,
        service,
        {CONF_DEVICE_ID: _device_id(hass, entry), **payload},
        blocking=True,
    )
    await hass.async_block_till_done()


async def test_maturity_follows_the_clock_and_publishes_its_window(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    entry = _make_entry("Garden Compost", "bin_garden")
    await _setup(hass, entry)

    # Nothing logged: there is no maturity to declare (docs/07 §9).
    fresh = hass.states.get(MATURITY_SENSOR)
    assert fresh is not None
    assert fresh.state == STATE_UNKNOWN
    assert fresh.attributes["limitations"] == ["no_material_logged"]
    assert fresh.attributes["forecast"] is None

    events = _listen(hass, EVENT_COMPOST_EVENT)
    notifications = _listen(hass, EVENT_COMPOST_NOTIFICATION)

    base = datetime.now(UTC)
    with freeze_time(base) as frozen:
        await _call(hass, entry, "log_material", {"material_type": "food_scraps"})

        young = hass.states.get(MATURITY_SENSOR)
        assert young is not None
        assert young.state == STATE_UNKNOWN
        # MATURITY_MIN_ELAPSED has not passed: "not yet" is UNKNOWN.
        assert young.attributes["limitations"] == [
            "insufficient_maturity_evidence"
        ]

        # Ten quiet days later — an observation is enough to re-assess the
        # bin; feeding it again would restart the quiet period.
        frozen.move_to(base + timedelta(days=10))
        await _call(
            hass,
            entry,
            "log_observation",
            {"category": "structure", "value": "dark and crumbly"},
        )

    ready = hass.states.get(MATURITY_SENSOR)
    assert ready is not None
    assert ready.state == "ready_for_curing"
    assert ready.attributes["confidence"] == 55
    assert ready.attributes["provenance"] == "inferred"
    assert ready.attributes["method"] == "batch"
    assert ready.attributes["limitations"] == ["no_temperature_evidence"]

    # The forecast is a WINDOW with its own confidence — never a date
    # (docs/07 §12): 21 target − 10 elapsed = 11, ± 8 spread → 3–19 days.
    forecast = ready.attributes["forecast"]
    assert forecast == {
        "min_days": 3,
        "max_days": 19,
        "confidence": 39,  # (55 * 70 + 50) // 100
        "limitations": ["forecast_without_personal_baseline"],
    }

    # The bus tells the same story in machine codes (docs/10 §2).
    assert [item["type"] for item in events] == [
        "material_added",
        "cycle_started",
        "observation",
        "maturity_estimated",
    ]
    assert events[3]["before_state"] == "unknown"
    assert events[3]["after_state"] == "ready_for_curing"
    assert events[3]["source"] == "integration"
    assert all(item["bin_id"] == "bin_garden" for item in events)

    # …and the built-in channel renders it as its own category (docs/16).
    assert [item["category"] for item in notifications] == ["cycle", "maturity"]
    maturity_note = notifications[1]
    assert maturity_note["kind"] == "info"
    assert maturity_note["after_state"] == "ready_for_curing"
    assert maturity_note["confidence"] == 55

    # A reload is a baseline: the readiness survives, the event is not
    # replayed (PR-027) — under the same frozen clock, because in real time
    # this batch would be seconds old again and honestly UNKNOWN.
    with freeze_time(base + timedelta(days=10)):
        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    restored = hass.states.get(MATURITY_SENSOR)
    assert restored is not None
    assert restored.state == "ready_for_curing"
    assert len(events) == 4
