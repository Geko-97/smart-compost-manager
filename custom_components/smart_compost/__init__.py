"""Smart Compost Manager integration for Home Assistant.

One config entry = one compost bin. This module owns the HA-facing runtime
lifecycle; all reasoning lives in `.core`, which never imports Home Assistant.
"""

from __future__ import annotations

from homeassistant.const import CONF_NAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError
from homeassistant.helpers.typing import ConfigType

from .const import (
    CONF_BIN_ID,
    CONF_COMPOST_TYPE,
    CONF_LOCATION,
    CONF_METHOD,
    CONF_RAIN_EXPOSURE,
    CONF_SHELTER,
    CONF_SUN_EXPOSURE,
    DOMAIN,
)
from .coordinator import (
    BinRuntime,
    SmartCompostConfigEntry,
    SmartCompostCoordinator,
)
from .core.model import (
    CompostMethod,
    CompostType,
    EnvironmentProfile,
    Location,
    RainExposure,
    Shelter,
    SunExposure,
    enum_or_unknown,
)
from .services import async_register_services
from .store import BinStore

PLATFORMS: tuple[Platform, ...] = (Platform.SENSOR,)


def _method_or_none(raw: object) -> CompostMethod | None:
    """The composting method, or None when it was never configured.

    CompostMethod has no UNKNOWN member (it is a user choice), so a missing
    or corrupted value stays None instead of being read as a real mode
    (docs/04: unknown is a value, not a guess).
    """
    if isinstance(raw, CompostMethod):
        return raw
    if isinstance(raw, str):
        for member in CompostMethod:
            if member.value == raw:
                return member
    return None


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the service actions (available even with zero bins)."""
    async_register_services(hass)
    return True


async def async_setup_entry(
    hass: HomeAssistant, entry: SmartCompostConfigEntry
) -> bool:
    """Set up one compost bin from a config entry."""
    # Sensor bindings live in entry.options: changing them reloads the bin.
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    try:
        bin_id: str = entry.data[CONF_BIN_ID]
    except KeyError as err:
        raise ConfigEntryError(
            translation_domain=DOMAIN,
            translation_key="invalid_entry_data",
        ) from err

    profile = EnvironmentProfile(
        location=enum_or_unknown(Location, entry.data.get(CONF_LOCATION)),
        shelter=enum_or_unknown(Shelter, entry.data.get(CONF_SHELTER)),
        rain_exposure=enum_or_unknown(
            RainExposure, entry.data.get(CONF_RAIN_EXPOSURE)
        ),
        sun_exposure=enum_or_unknown(SunExposure, entry.data.get(CONF_SUN_EXPOSURE)),
        method=_method_or_none(entry.data.get(CONF_METHOD)),
    )

    store = BinStore(hass, entry.entry_id)
    records = await store.async_load()

    coordinator = SmartCompostCoordinator(hass, entry, profile, records, store)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = BinRuntime(
        bin_id=bin_id,
        device_name=str(entry.data.get(CONF_NAME, entry.title)),
        device_model=enum_or_unknown(
            CompostType, entry.data.get(CONF_COMPOST_TYPE)
        ).value,
        coordinator=coordinator,
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: SmartCompostConfigEntry
) -> bool:
    """Unload a compost bin config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_update_listener(
    hass: HomeAssistant, entry: SmartCompostConfigEntry
) -> None:
    """Reload the bin when its entry changes (options / sensor bindings)."""
    await hass.config_entries.async_reload(entry.entry_id)
