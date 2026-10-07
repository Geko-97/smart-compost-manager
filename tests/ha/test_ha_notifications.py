"""End-to-end M6: bus events, built-in notifications, no spam (docs/16).

Sequence coverage (docs/20 §8, §11, §12): a logged material publishes an
event with the right bin identity; a state condition waits out the
persistence window before notifying and then deduplicates; the built-in
channel can be switched off while the bus stays alive; history and engine
memory survive a reload without duplicating; corrupt storage cannot take
the integration down.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from freezegun import freeze_time
from homeassistant.components import persistent_notification
from homeassistant.const import ATTR_UNIT_OF_MEASUREMENT
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.smart_compost.const import (
    DOMAIN,
    EVENT_COMPOST_EVENT,
    EVENT_COMPOST_NOTIFICATION,
)

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


def _listen(hass: HomeAssistant, signal: str) -> list[dict[str, Any]]:
    """Collect fired payloads in dispatch order.

    The listener is a `@callback`, so the bus runs it inline on the event
    loop: an unadorned callable is an executor job, where two deliveries
    may race and be appended out of order (the bus always fires in order).
    """
    captured: list[dict[str, Any]] = []

    @callback
    def _record(event: Any) -> None:
        captured.append(event.data)

    hass.bus.async_listen(signal, _record)
    return captured


def _listen_notifications(hass: HomeAssistant) -> list[dict[str, Any]]:
    """Collect what the built-in channel renders (public callback API)."""
    collected: list[dict[str, Any]] = []

    def _record(_update_type, items: dict[str, dict[str, Any]]) -> None:
        collected.extend(items.values())

    persistent_notification.async_register_callback(hass, _record)
    return collected


async def _log_material(
    hass: HomeAssistant, entry: MockConfigEntry, kind: str = "food_scraps"
) -> None:
    device = dr.async_get(hass).async_get_device_by_identifier(
        (DOMAIN, entry.unique_id), entry.entry_id
    )
    assert device is not None
    await hass.services.async_call(
        DOMAIN,
        "log_material",
        {"device_id": device.id, "material_type": kind},
        blocking=True,
    )
    await hass.async_block_till_done()


def _by_category(
    captured: list[dict[str, Any]], category: str
) -> list[dict[str, Any]]:
    return [item for item in captured if item["category"] == category]


# --- A logged material becomes events, isolated per bin ----------------------


async def test_material_log_fires_bus_events_and_renders_a_notification(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    entry_a = _make_entry("Alpha Compost", "bin_alpha")
    entry_b = _make_entry("Beta Compost", "bin_beta")
    await _setup(hass, entry_a)
    await _setup(hass, entry_b)

    events = _listen(hass, EVENT_COMPOST_EVENT)
    notifications = _listen(hass, EVENT_COMPOST_NOTIFICATION)
    rendered = _listen_notifications(hass)

    await _log_material(hass, entry_a)

    # The human action and the engine's reaction, both with metadata
    # (docs/10 §4) and the right origin (docs/10 §5).
    types = [item["type"] for item in events]
    assert types == ["material_added", "cycle_started"]
    material = events[0]
    assert material["source"] == "manual"
    assert material["bin_id"] == "bin_alpha"
    assert material["reason"] == "food_scraps"
    assert material["cycle_id"] is None
    cycle = events[1]
    assert cycle["source"] == "integration"
    assert cycle["before_state"] == "new"
    assert cycle["after_state"] == "active"

    # Multi-bin isolation (docs/20 §8): bin B never hears any of this.
    assert all(item["bin_id"] == "bin_alpha" for item in events)
    assert all(item["bin_id"] == "bin_alpha" for item in notifications)

    # The built-in channel renders a translated message (docs/16 §5).
    cycle_notes = _by_category(notifications, "cycle")
    assert len(cycle_notes) == 1
    assert cycle_notes[0]["kind"] == "info"
    assert cycle_notes[0]["severity"] == "info"
    # Hand-computed: no domains → 100 * 0.5 * (1 evidence / 3) = 17.
    assert cycle_notes[0]["confidence"] == 17
    assert len(rendered) == 1
    rendered_cycle = rendered[0]
    assert rendered_cycle["notification_id"] == (
        f"{DOMAIN}_{entry_a.entry_id}_cycle"
    )
    assert rendered_cycle["title"] == "New compost cycle"
    assert (
        rendered_cycle["message"]
        == "A new cycle started at Alpha Compost. Confidence: 17%."
    )

    # Everything is persisted per bin (docs/19): events + engine memory.
    stored = hass_storage[f"{DOMAIN}.{entry_a.entry_id}"]["data"]
    assert [item["type"] for item in stored["events"]] == [
        "material_added",
        "cycle_started",
    ]
    assert stored["events"][0]["bin_id"] == "bin_alpha"
    assert stored["notification_states"]["cycle"]["notified"] is False
    assert stored["notification_states"]["cycle"]["last_sent"] is not None

    stored_b = hass_storage.get(f"{DOMAIN}.{entry_b.entry_id}")
    assert stored_b is None or stored_b["data"]["events"] == []


# --- A state condition waits, then notifies once -----------------------------


async def test_rapid_heating_respects_persistence_and_deduplicates(
    hass: HomeAssistant,
) -> None:
    entry = _make_entry("Garden Compost", "bin_garden")
    await _setup(hass, entry)

    notifications = _listen(hass, EVENT_COMPOST_NOTIFICATION)
    rendered = _listen_notifications(hass)

    base = datetime.now(UTC)
    with freeze_time(base) as frozen:
        _set_temperature(hass, "30")
        await _configure_options(
            hass,
            entry,
            {"temperature_entity": [TEMPERATURE_ENTITY], "moisture_entity": []},
        )

        # 6 samples over 75 min → slope 12 °C/h at step 5: the diagnostic
        # appears, but persistence (15 min) has just started.
        for step, value in enumerate((33, 36, 39, 42, 45), start=1):
            frozen.move_to(base + timedelta(minutes=15 * step))
            _set_temperature(hass, str(value))
            await hass.async_block_till_done()

        assert _by_category(notifications, "rapid_heating") == []
        # The phase DID change to thermophilic (its own INFO pulse)…
        thermophilic = _by_category(notifications, "thermophilic")
        assert len(thermophilic) == 1
        assert thermophilic[0]["confidence"] == 70  # 2 phase signals

        # …15 minutes later the heating condition is mature: one ISSUE.
        frozen.move_to(base + timedelta(minutes=90))
        _set_temperature(hass, "48")
        await hass.async_block_till_done()

        heating = _by_category(notifications, "rapid_heating")
        assert len(heating) == 1
        issue = heating[0]
        assert issue["kind"] == "issue"
        assert issue["severity"] == "suggestion"
        assert issue["confidence"] == 70  # fast_rise + elevated_now
        assert issue["action"] == "none"
        assert "fast_rise" in issue["reasons"]
        assert "elevated_now" in issue["reasons"]
        assert issue["bin_id"] == "bin_garden"

        # Still rising a sample later: deduplication, no repeat (docs/16 §7).
        frozen.move_to(base + timedelta(minutes=105))
        _set_temperature(hass, "51")
        await hass.async_block_till_done()
        assert len(_by_category(notifications, "rapid_heating")) == 1

    # The built-in message is the translated one (docs/16 §5 what/why).
    heating_cards = [
        card
        for card in rendered
        if card["notification_id"].endswith("_rapid_heating")
    ]
    assert len(heating_cards) == 1
    assert heating_cards[0]["title"] == "Rapid heating detected"
    assert "The compost in Garden Compost is heating up fast." in (
        heating_cards[0]["message"]
    )
    assert "Confidence: 70%." in heating_cards[0]["message"]


# --- The built-in channel is opt-in, the bus never is ------------------------


async def test_disabling_built_in_notifications_keeps_the_bus_alive(
    hass: HomeAssistant,
) -> None:
    entry = _make_entry("Garden Compost", "bin_garden")
    await _setup(hass, entry)
    result = await _configure_options(
        hass, entry, {"notification_categories": []}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY

    notifications = _listen(hass, EVENT_COMPOST_NOTIFICATION)
    rendered = _listen_notifications(hass)
    await _log_material(hass, entry)

    # Custom automations still receive the decision (docs/16 §8)…
    assert len(_by_category(notifications, "cycle")) == 1
    # …but nothing is pushed into Home Assistant's notification feed.
    assert rendered == []


# --- Reload: no loss, no duplication (PR-027) --------------------------------


async def test_history_and_engine_memory_survive_reload_without_duplicates(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    entry = _make_entry("Garden Compost", "bin_garden")
    await _setup(hass, entry)

    events = _listen(hass, EVENT_COMPOST_EVENT)
    notifications = _listen(hass, EVENT_COMPOST_NOTIFICATION)

    await _log_material(hass, entry, "food_scraps")
    assert [item["type"] for item in events] == [
        "material_added",
        "cycle_started",
    ]

    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    # The second addition continues history — cycle_started is not replayed.
    await _log_material(hass, entry, "dry_leaves")
    types = [item["type"] for item in events]
    assert types == [
        "material_added",
        "cycle_started",
        "material_added",
    ]
    # The cycle pulse was already spent: still exactly one notification.
    assert len(_by_category(notifications, "cycle")) == 1

    stored = hass_storage[f"{DOMAIN}.{entry.entry_id}"]["data"]
    assert [item["type"] for item in stored["events"]] == [
        "material_added",
        "cycle_started",
        "material_added",
    ]
    assert stored["materials"][1]["material_type"] == "dry_leaves"
    last_sent = stored["notification_states"]["cycle"]["last_sent"]
    assert last_sent is not None


# --- Corruption never takes the integration down (docs/19 §9) ----------------


async def test_corrupt_storage_is_skipped_and_the_bin_still_starts(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    entry = _make_entry("Garden Compost", "bin_garden")
    hass_storage[f"{DOMAIN}.{entry.entry_id}"] = {
        "version": 1,
        "data": {
            "materials": "not-a-list",
            "events": [{"type": "who_knows"}],
            "notification_states": {"no_such_category": {"notified": True}},
            "temperature": [{"value": "high"}],
        },
    }

    await _setup(hass, entry)

    health = hass.states.get("sensor.garden_compost_health")
    phase = hass.states.get("sensor.garden_compost_phase")
    assert health is not None and phase is not None
    # Nothing corrupt was adopted: the bin starts honest and empty.
    assert phase.attributes["sample_count"] == 0
    await _log_material(hass, entry)
    stored = hass_storage[f"{DOMAIN}.{entry.entry_id}"]["data"]
    assert [item["type"] for item in stored["events"]] == [
        "material_added",
        "cycle_started",
    ]
