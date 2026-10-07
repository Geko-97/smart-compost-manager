"""Constants for Smart Compost Manager."""

from __future__ import annotations

DOMAIN = "smart_compost"

# Config entry data keys. One config entry = one compost bin (isolation unit).
CONF_BIN_ID = "bin_id"
CONF_COMPOST_TYPE = "compost_type"
CONF_METHOD = "method"
CONF_LOCATION = "location"
CONF_SHELTER = "shelter"
CONF_RAIN_EXPOSURE = "rain_exposure"
CONF_SUN_EXPOSURE = "sun_exposure"

# Options flow: bindings to EXISTING Home Assistant sensors (read-only).
CONF_TEMPERATURE_ENTITY = "temperature_entity"
CONF_MOISTURE_ENTITY = "moisture_entity"
CONF_VOC_ENTITY = "voc_entity"
CONF_AMMONIA_ENTITY = "ammonia_entity"
CONF_FILL_ENTITY = "fill_entity"

# Options flow: built-in notification categories the user opted into.
CONF_NOTIFICATION_CATEGORIES = "notification_categories"

# Bus events (docs/10, docs/16 §8): the custom-automation channel. payloads
# carry machine-readable codes only — text lives in translations.
EVENT_COMPOST_EVENT = f"{DOMAIN}_event"
EVENT_COMPOST_NOTIFICATION = f"{DOMAIN}_notification"
