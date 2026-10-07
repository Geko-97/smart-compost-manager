"""End-to-end M7: the batch-cycle lifecycle, reports and isolation (docs/11).

Sequence coverage: an explicit start opens a report window, a completion
closes it with an optional output, the second cycle is compared against the
first of the SAME bin, a baseline appears only from the third completed
cycle, and none of it ever crosses a bin boundary.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from freezegun import freeze_time
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_DEVICE_ID, STATE_UNKNOWN
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.smart_compost.const import DOMAIN, EVENT_COMPOST_EVENT

REPORT_SENSOR = "sensor.garden_compost_cycle_report"


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


def _stored(hass_storage: dict[str, Any], entry: MockConfigEntry) -> dict:
    key = f"{DOMAIN}.{entry.entry_id}"
    assert key in hass_storage, f"store key missing: {key}"
    return hass_storage[key]["data"]


def _report(hass: HomeAssistant):
    state = hass.states.get(REPORT_SENSOR)
    assert state is not None
    return state


async def _start(hass: HomeAssistant, entry: MockConfigEntry, **extra: Any) -> None:
    await hass.services.async_call(
        DOMAIN,
        "start_cycle",
        {CONF_DEVICE_ID: _device_id(hass, entry), **extra},
        blocking=True,
    )
    await hass.async_block_till_done()


async def _complete(
    hass: HomeAssistant, entry: MockConfigEntry, **extra: Any
) -> None:
    await hass.services.async_call(
        DOMAIN,
        "complete_cycle",
        {CONF_DEVICE_ID: _device_id(hass, entry), **extra},
        blocking=True,
    )
    await hass.async_block_till_done()


async def _feed(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    *,
    quantity: float,
    unit: str,
) -> None:
    await hass.services.async_call(
        DOMAIN,
        "log_material",
        {
            CONF_DEVICE_ID: _device_id(hass, entry),
            "material_type": "food_scraps",
            "quantity": quantity,
            "quantity_unit": unit,
        },
        blocking=True,
    )
    await hass.async_block_till_done()


def _listen(hass: HomeAssistant, signal: str) -> list[dict[str, Any]]:
    """Collect fired payloads in dispatch order (see test_ha_notifications)."""
    captured: list[dict[str, Any]] = []

    @callback
    def _record(event: Any) -> None:
        captured.append(event.data)

    hass.bus.async_listen(signal, _record)
    return captured


# --- One cycle: start → feed → complete --------------------------------------


async def test_cycle_lifecycle_updates_the_report_and_persists(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    entry = _make_entry("Garden Compost", "bin_garden")
    await _setup(hass, entry)
    events = _listen(hass, EVENT_COMPOST_EVENT)

    # Nothing started yet: UNKNOWN, never a fabricated 0 (docs/04).
    assert _report(hass).state == STATE_UNKNOWN

    base = datetime.now(UTC)
    with freeze_time(base) as frozen:
        await _start(hass, entry, notes="autumn batch")
        started = _report(hass)
        assert started.state != STATE_UNKNOWN
        cycle_id = started.state
        assert started.attributes["status"] == "active"
        assert started.attributes["started_at"] == base.isoformat()
        assert started.attributes["completed_at"] is None
        assert started.attributes["duration_days"] == 0.0
        assert started.attributes["output"] is None
        assert started.attributes["comparison"] is None
        assert started.attributes["baseline"] is None
        # No sensor: the report says so instead of inventing thermal facts.
        assert started.attributes["limitations"] == ["no_temperature_data"]

        # Only one window can be open at a time (docs/11 §6).
        with pytest.raises(ServiceValidationError):
            await _start(hass, entry)

        # Records logged while the window is open belong to this cycle.
        await hass.services.async_call(
            DOMAIN,
            "log_material",
            {
                CONF_DEVICE_ID: _device_id(hass, entry),
                "material_type": "food_scraps",
                "quantity": 2,
                "quantity_unit": "bucket",
            },
            blocking=True,
        )
        await hass.async_block_till_done()
        fed = _report(hass)
        assert fed.state == cycle_id
        assert fed.attributes["material_count"] == 1
        # Amounts summed per unit inside the window (docs/11 §7).
        assert fed.attributes["material_quantity"] == {"bucket": 2.0}

        frozen.move_to(base + timedelta(days=10))
        await _complete(
            hass,
            entry,
            output_quantity=40,
            output_unit="litre",
            output_destination="raised_bed",
        )

    done = _report(hass)
    assert done.state == cycle_id
    assert done.attributes["status"] == "completed"
    assert done.attributes["duration_days"] == 10.0
    assert done.attributes["material_count"] == 1
    assert done.attributes["observation_count"] == 0
    assert done.attributes["intervention_count"] == 0
    assert done.attributes["material_quantity"] == {"bucket": 2.0}
    assert done.attributes["completed_at"] == (base + timedelta(days=10)).isoformat()
    assert done.attributes["output"] == {
        "quantity_value": 40.0,
        "quantity_unit": "litre",
        "destination": "raised_bed",
        "notes": None,
    }
    # First cycle: nothing to compare against, nothing to baseline on.
    assert done.attributes["comparison"] is None
    assert done.attributes["baseline"] is None

    # The bus tells the same story in machine codes (docs/10 §5).
    assert [item["type"] for item in events] == [
        "cycle_started",
        "material_added",
        "cycle_completed",
        # M8: ten quiet days with no sensor is honestly "ready for curing"
        # — the readiness change is published like every other transition.
        "maturity_estimated",
    ]
    assert events[0]["source"] == "manual"
    assert events[0]["notes"] == "autumn batch"
    assert events[0]["cycle_id"] == cycle_id
    assert events[1]["cycle_id"] is None  # the log itself carries no cycle
    assert events[2]["source"] == "manual"
    assert events[2]["cycle_id"] == cycle_id
    assert events[2]["before_state"] == "active"
    assert events[2]["after_state"] == "completed"
    assert events[2]["reason"] == "output_logged"
    assert events[3]["source"] == "integration"
    assert events[3]["before_state"] == "unknown"
    assert events[3]["after_state"] == "ready_for_curing"
    assert events[3]["reason"] == "readiness_changed"
    assert all(item["bin_id"] == "bin_garden" for item in events)

    # Persisted per bin (docs/19): the window and its output survive.
    cycles = _stored(hass_storage, entry)["cycles"]
    assert len(cycles) == 1
    assert cycles[0]["id"] == cycle_id
    assert cycles[0]["status"] == "completed"
    assert cycles[0]["completed_at"] is not None
    assert cycles[0]["output"]["quantity_value"] == 40.0
    assert cycles[0]["output"]["destination"] == "raised_bed"


async def test_completing_without_an_active_cycle_is_rejected(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    entry = _make_entry("Garden Compost", "bin_garden")
    await _setup(hass, entry)

    # Explicit error instead of a fabricated completion (docs/04).
    with pytest.raises(ServiceValidationError):
        await _complete(hass, entry)

    assert _report(hass).state == STATE_UNKNOWN
    assert f"{DOMAIN}.{entry.entry_id}" not in hass_storage


async def test_completion_without_output_stays_unknown(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    entry = _make_entry("Garden Compost", "bin_garden")
    await _setup(hass, entry)

    await _start(hass, entry)
    await _complete(hass, entry)

    state = _report(hass)
    assert state.attributes["status"] == "completed"
    # No measured output: None, never 0 (docs/04).
    assert state.attributes["output"] is None

    events = [item["type"] for item in _stored(hass_storage, entry)["events"]]
    assert events == ["cycle_started", "cycle_completed"]
    stored = _stored(hass_storage, entry)["cycles"][0]
    assert stored["output"] is None


# --- Comparison and baseline from this bin's own cycles ----------------------


async def test_second_cycle_is_compared_against_the_first_of_the_same_bin(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    entry = _make_entry("Garden Compost", "bin_garden")
    await _setup(hass, entry)

    base = datetime.now(UTC)
    with freeze_time(base) as frozen:
        await _start(hass, entry)
        await _feed(hass, entry, quantity=3, unit="litre")
        frozen.move_to(base + timedelta(days=10))
        await _complete(hass, entry)
        first_id = _report(hass).state

        frozen.move_to(base + timedelta(days=20))
        await _start(hass, entry)
        await _feed(hass, entry, quantity=5, unit="litre")
        frozen.move_to(base + timedelta(days=25))
        await _complete(hass, entry)

    state = _report(hass)
    assert state.state != first_id
    comparison = state.attributes["comparison"]
    assert comparison["previous_cycle_id"] == first_id
    # 5 days against 10 days (docs/18 §3: same bin only, plain deltas).
    assert comparison["duration_days_delta"] == -5.0
    assert comparison["material_count_delta"] == 0
    assert comparison["intervention_count_delta"] == 0
    # Neither side has thermal data: unknown stays unknown.
    assert comparison["peak_delta"] is None
    assert comparison["thermophilic_hours_delta"] is None
    # 5 litres against 3 litres — the same unit on both sides.
    assert comparison["material_quantity_delta"] == 2.0
    # Two completed cycles are still below BASELINE_MIN_CYCLES.
    assert state.attributes["baseline"] is None
    assert len(_stored(hass_storage, entry)["cycles"]) == 2


async def test_third_completed_cycle_creates_the_personal_baseline(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    entry = _make_entry("Garden Compost", "bin_garden")
    await _setup(hass, entry)

    base = datetime.now(UTC)
    with freeze_time(base) as frozen:
        for start_days, duration_days in (
            (0, 10),
            (20, 5),
            (30, 6),
        ):
            frozen.move_to(base + timedelta(days=start_days))
            await _start(hass, entry)
            frozen.move_to(base + timedelta(days=start_days + duration_days))
            await _complete(hass, entry)

    state = _report(hass)
    assert state.attributes["status"] == "completed"
    baseline = state.attributes["baseline"]
    # docs/18 §4: below three completed cycles there is no baseline at all.
    assert baseline["completed_cycles"] == 3
    # min(3, 5) * 20 = 60 (docs/18 §6 confidence growth).
    assert baseline["confidence"] == 60
    # Durations 10 / 5 / 6 days → median 6.0.
    assert baseline["median_duration_days"] == 6.0
    # No temperature history: the thermal median stays UNKNOWN with a reason.
    assert baseline["median_peak"] is None
    assert baseline["limitations"] == ["insufficient_thermal_cycles"]

    # The report still points at the newest completed cycle.
    comparison = state.attributes["comparison"]
    assert comparison["previous_cycle_id"] == _stored(
        hass_storage, entry
    )["cycles"][1]["id"]


# --- Reload and isolation ----------------------------------------------------


async def test_cycles_survive_a_reload_without_replay(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    entry = _make_entry("Garden Compost", "bin_garden")
    await _setup(hass, entry)

    await _start(hass, entry, notes="winter batch")
    await _complete(hass, entry)
    cycle_id = _report(hass).state

    events = _listen(hass, EVENT_COMPOST_EVENT)
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    restored = _report(hass)
    assert restored.state == cycle_id
    assert restored.attributes["status"] == "completed"
    # A reload is a baseline: no transition is replayed (PR-027).
    assert [item["type"] for item in events] == []
    assert len(_stored(hass_storage, entry)["cycles"]) == 1

    # The cycle can continue: a new window opens on the restored history.
    await _start(hass, entry)
    state = _report(hass)
    assert state.state != cycle_id
    assert state.attributes["status"] == "active"
    assert state.attributes["comparison"]["previous_cycle_id"] == cycle_id
    assert len(_stored(hass_storage, entry)["cycles"]) == 2


async def test_cycles_never_cross_a_bin_boundary(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    entry_a = _make_entry("Alpha Compost", "bin_alpha")
    entry_b = _make_entry("Beta Compost", "bin_beta")
    await _setup(hass, entry_a)
    await _setup(hass, entry_b)

    events = _listen(hass, EVENT_COMPOST_EVENT)
    await _start(hass, entry_a)

    report_a = hass.states.get("sensor.alpha_compost_cycle_report")
    report_b = hass.states.get("sensor.beta_compost_cycle_report")
    assert report_a is not None and report_a.state != STATE_UNKNOWN
    # Bin B knows nothing about bin A's batch (docs/11 §2).
    assert report_b is not None and report_b.state == STATE_UNKNOWN
    assert report_b.attributes.get("status") is None

    assert all(item["bin_id"] == "bin_alpha" for item in events)
    assert len(_stored(hass_storage, entry_a)["cycles"]) == 1
    assert f"{DOMAIN}.{entry_b.entry_id}" not in hass_storage
