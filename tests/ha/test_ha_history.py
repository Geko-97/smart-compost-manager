"""End-to-end M5: a bound sensor builds history that drives real entities.

Sequence: bind an existing temperature sensor, watch samples accumulate
rate-limited into the bounded series, then check that phase, trend and the
multi-signal diagnosis reach the entities — and that the history survives
an unload/setup cycle (docs/10, docs/19).

Expected numbers are hand-computed from `core/constants.py`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from freezegun import freeze_time
from homeassistant.const import ATTR_UNIT_OF_MEASUREMENT, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
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


async def test_history_drives_phase_trend_and_diagnostics(hass: HomeAssistant) -> None:
    entry = _make_entry("Garden Compost", "bin_garden")
    await _setup(hass, entry)

    base = datetime.now(UTC)
    with freeze_time(base) as frozen:
        _set_temperature(hass, "30")

        # Without the binding there is no measurement and no phase.
        phase = hass.states.get("sensor.garden_compost_phase")
        assert phase is not None and phase.state == STATE_UNKNOWN

        result = await _configure_options(
            hass,
            entry,
            {"temperature_entity": [TEMPERATURE_ENTITY], "moisture_entity": []},
        )
        assert result["type"] is FlowResultType.CREATE_ENTRY

        # 9 samples in total: one at setup, then 8 more 15 minutes apart,
        # rising 30 → 46 °C (8 °C/h).
        for step in range(1, 9):
            frozen.move_to(base + timedelta(minutes=15 * step))
            _set_temperature(hass, str(30 + 2 * step))
            await hass.async_block_till_done()

        phase = hass.states.get("sensor.garden_compost_phase")
        assert phase is not None
        assert phase.state == "thermophilic"
        assert phase.attributes["provenance"] == "inferred"
        # Two signals: current_high (46 ≥ 40) + significant_peak (≥ 45).
        assert phase.attributes["confidence"] == 70
        assert phase.attributes["limitations"] == []
        assert [item["parameter"] for item in phase.attributes["why"]] == [
            "current_high",
            "significant_peak",
        ]
        # Trend facts on the same entity (docs/10).
        assert phase.attributes["trend"] == "rising"
        assert phase.attributes["slope_per_hour"] == 8.0
        assert phase.attributes["sample_count"] == 9
        assert phase.attributes["peak_value"] == 46.0
        # 40 °C is reached at +75 min, then 45 min above (0.75 h).
        assert phase.attributes["time_above_thermophilic_hours"] == 0.75
        assert phase.attributes["time_above_hot_hours"] == 0.0

        health = hass.states.get("sensor.garden_compost_health")
        assert health is not None
        # Band for 46 °C is 90; the 8 °C/h rise caps it at 55 (docs/06).
        assert health.state == "55"
        assert health.attributes["domain_scores"]["thermal"] == 55
        # Enough history: the trend limitation is gone.
        assert "no_temperature_trend" not in health.attributes["limitations"]
        # Two signals corroborate the diagnosis: fast_rise + elevated_now.
        assert health.attributes["diagnostics"] == [
            {
                "code": "rapid_heating",
                "confidence": 70,
                "signals": ["fast_rise", "elevated_now"],
            }
        ]

        confidence = hass.states.get("sensor.garden_compost_confidence")
        data_quality = hass.states.get("sensor.garden_compost_data_quality")
        # DQ: 100 * (0.5 * 1/2 measured coverage) = 25.
        assert data_quality is not None and data_quality.state == "25"
        # Confidence: 100 * (0.5 * 1/6 + 0.5 * 3/3) = 58 — the findings
        # never pad it (docs/06).
        assert confidence is not None and confidence.state == "58"

        # The series is persisted per bin: unload, set up again, still there.
        await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        phase = hass.states.get("sensor.garden_compost_phase")
        assert phase is not None
        assert phase.state == "thermophilic"
        # The re-recorded first reading is a duplicate: no extra sample.
        assert phase.attributes["sample_count"] == 9
        assert phase.attributes["trend"] == "rising"
