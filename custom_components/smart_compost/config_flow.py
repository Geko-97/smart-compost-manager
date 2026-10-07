"""Config flow: creates one config entry per compost bin (docs/14).

Two steps — bin identity, then environment. Physical sensors are bound
afterwards through the options flow (read-only: the integration never
creates physical sensor copies).
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Any

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)
from probatio import All, Length, Optional, Required, Schema

from .const import (
    CONF_AMMONIA_ENTITY,
    CONF_BIN_ID,
    CONF_COMPOST_TYPE,
    CONF_FILL_ENTITY,
    CONF_LOCATION,
    CONF_METHOD,
    CONF_MOISTURE_ENTITY,
    CONF_NOTIFICATION_CATEGORIES,
    CONF_RAIN_EXPOSURE,
    CONF_SHELTER,
    CONF_SUN_EXPOSURE,
    CONF_TEMPERATURE_ENTITY,
    CONF_VOC_ENTITY,
    DOMAIN,
)
from .core.model import (
    CompostMethod,
    CompostType,
    Location,
    RainExposure,
    Shelter,
    SunExposure,
)
from .core.notifications import NotificationCategory


def _select(translation_key: str, values: list[str]) -> SelectSelector:
    """Dropdown whose labels are translated via strings.json selectors."""
    return SelectSelector(
        SelectSelectorConfig(
            options=values,
            mode=SelectSelectorMode.DROPDOWN,
            translation_key=translation_key,
        )
    )


USER_SCHEMA = Schema(
    {
        Required(CONF_NAME, default="Compost bin"): All(str, Length(min=1)),
        Required(CONF_COMPOST_TYPE, default=CompostType.ENCLOSED_BIN.value): _select(
            "compost_type", [member.value for member in CompostType]
        ),
        Required(CONF_METHOD, default=CompostMethod.CONTINUOUS.value): _select(
            "compost_method", [member.value for member in CompostMethod]
        ),
    }
)

ENVIRONMENT_SCHEMA = Schema(
    {
        Required(CONF_LOCATION, default=Location.OUTDOOR.value): _select(
            "location", [member.value for member in Location]
        ),
        Required(CONF_SHELTER, default=Shelter.UNKNOWN.value): _select(
            "shelter", [member.value for member in Shelter]
        ),
        Required(CONF_RAIN_EXPOSURE, default=RainExposure.UNKNOWN.value): _select(
            "rain_exposure", [member.value for member in RainExposure]
        ),
        Required(CONF_SUN_EXPOSURE, default=SunExposure.UNKNOWN.value): _select(
            "sun_exposure", [member.value for member in SunExposure]
        ),
    }
)


class SmartCompostConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the configuration of one compost bin."""

    VERSION = 1

    def __init__(self) -> None:
        self._identity: dict[str, Any] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Bin identity: name, type, method."""
        if user_input is not None:
            self._identity = user_input
            return await self.async_step_environment()
        return self.async_show_form(step_id="user", data_schema=USER_SCHEMA)

    async def async_step_environment(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Environment: where the bin lives (defaults stay UNKNOWN)."""
        if user_input is not None:
            bin_id = uuid.uuid4().hex
            # One entry per bin; the unique id ties registry data to the bin.
            await self.async_set_unique_id(bin_id)
            name = str(self._identity[CONF_NAME])
            return self.async_create_entry(
                title=name,
                data={
                    CONF_BIN_ID: bin_id,
                    CONF_NAME: name,
                    CONF_COMPOST_TYPE: self._identity[CONF_COMPOST_TYPE],
                    CONF_METHOD: self._identity[CONF_METHOD],
                    **user_input,
                },
            )
        return self.async_show_form(
            step_id="environment", data_schema=ENVIRONMENT_SCHEMA
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> SmartCompostOptionsFlow:
        """Return the options flow (sensor bindings)."""
        return SmartCompostOptionsFlow()


def _entity_list(current: Mapping[str, Any], key: str) -> list[str]:
    """Current binding stored as a list of entity ids."""
    value = current.get(key)
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str)]
    return []


def _category_list(current: Mapping[str, Any]) -> list[str]:
    """Enabled built-in notification categories; all on by default.

    An explicit empty list is a legitimate value (everything off) and is
    preserved — the default only applies before the user ever saves.
    """
    value = current.get(CONF_NOTIFICATION_CATEGORIES)
    if isinstance(value, list):
        return [str(item) for item in value]
    return [member.value for member in NotificationCategory]


#: One config-entry key per bound input, in form order (M9: VOC, ammonia
#: and fill are read exactly like temperature and moisture — read-only,
#: fresh-only, unit-checked downstream).
_BINDING_KEYS = (
    CONF_TEMPERATURE_ENTITY,
    CONF_MOISTURE_ENTITY,
    CONF_VOC_ENTITY,
    CONF_AMMONIA_ENTITY,
    CONF_FILL_ENTITY,
)


def _options_schema(current: Mapping[str, Any]) -> Schema:
    """Options form: bind existing sensors, pick notification categories."""
    sensor = EntitySelector(
        EntitySelectorConfig(domain="sensor", multiple=True)
    )
    categories = SelectSelector(
        SelectSelectorConfig(
            options=[member.value for member in NotificationCategory],
            multiple=True,
            translation_key="notification_category",
        )
    )
    return Schema(
        {
            Optional(
                CONF_TEMPERATURE_ENTITY,
                default=_entity_list(current, CONF_TEMPERATURE_ENTITY),
            ): sensor,
            Optional(
                CONF_MOISTURE_ENTITY,
                default=_entity_list(current, CONF_MOISTURE_ENTITY),
            ): sensor,
            Optional(
                CONF_VOC_ENTITY,
                default=_entity_list(current, CONF_VOC_ENTITY),
            ): sensor,
            Optional(
                CONF_AMMONIA_ENTITY,
                default=_entity_list(current, CONF_AMMONIA_ENTITY),
            ): sensor,
            Optional(
                CONF_FILL_ENTITY,
                default=_entity_list(current, CONF_FILL_ENTITY),
            ): sensor,
            Optional(
                CONF_NOTIFICATION_CATEGORIES,
                default=_category_list(current),
            ): categories,
        }
    )


class SmartCompostOptionsFlow(OptionsFlow):
    """Bind existing Home Assistant sensors to one compost bin."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            # One physical sensor may feed only ONE input: `read_bindings`
            # maps entity → kind, so a reused sensor would silently turn a
            # VOC reading into a moisture reading (M9).
            bound: dict[str, str] = {}
            for key in _BINDING_KEYS:
                entities = _entity_list(user_input, key)
                if not entities:
                    continue
                entity_id = entities[0]
                if entity_id in bound:
                    return self.async_show_form(
                        step_id="init",
                        data_schema=_options_schema(user_input),
                        errors={"base": "same_sensor"},
                    )
                bound[entity_id] = key
            return self.async_create_entry(title="", data=user_input)
        return self.async_show_form(
            step_id="init", data_schema=_options_schema(self.config_entry.options)
        )
