"""Config flow tests: two steps, one entry per bin, defaults are safe."""

from __future__ import annotations

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.smart_compost.const import (
    CONF_BIN_ID,
    CONF_COMPOST_TYPE,
    CONF_METHOD,
    DOMAIN,
)


async def test_full_flow_creates_one_bin(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"name": "Garden Compost", "compost_type": "tumbler", "method": "batch"},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "environment"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "location": "outdoor",
            "shelter": "sheltered",
            "rain_exposure": "partial",
            "sun_exposure": "shade",
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Garden Compost"
    assert result["data"][CONF_BIN_ID]
    assert result["data"][CONF_COMPOST_TYPE] == "tumbler"
    assert result["data"][CONF_METHOD] == "batch"
    assert result["data"]["sun_exposure"] == "shade"

    await hass.async_block_till_done()

    entry = hass.config_entries.async_entries(DOMAIN)[0]
    assert entry.state is config_entries.ConfigEntryState.LOADED
    # The unique id ties registry and device data to this exact bin.
    assert entry.unique_id == result["data"][CONF_BIN_ID]


async def test_flow_defaults_complete_every_step(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "environment"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Compost bin"
    assert result["data"][CONF_COMPOST_TYPE] == "enclosed_bin"
    assert result["data"][CONF_METHOD] == "continuous"
    # Safe defaults: only location suggests outdoors, the rest stays unknown.
    assert result["data"]["location"] == "outdoor"
    assert result["data"]["shelter"] == "unknown"
    assert result["data"]["rain_exposure"] == "unknown"
    assert result["data"]["sun_exposure"] == "unknown"
