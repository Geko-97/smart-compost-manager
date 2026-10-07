"""Translation integrity: strings.json ↔ translations/en.json ↔ code."""

from __future__ import annotations

import json
import string
from pathlib import Path

import yaml

from custom_components.smart_compost.core.model import (
    ActionCode,
    CompostMethod,
    CompostType,
    CycleStage,
    Location,
    RainExposure,
    Shelter,
    SunExposure,
)
from custom_components.smart_compost.core.notifications import (
    NOTIFICATION_MESSAGE_KEYS,
    NotificationCategory,
)
from custom_components.smart_compost.sensor import SENSORS
from custom_components.smart_compost.services import (
    COMPLETE_CYCLE_SCHEMA,
    LOG_INTERVENTION_SCHEMA,
    LOG_MATERIAL_SCHEMA,
    LOG_OBSERVATION_SCHEMA,
    SERVICE_COMPLETE_CYCLE,
    SERVICE_LOG_INTERVENTION,
    SERVICE_LOG_MATERIAL,
    SERVICE_LOG_OBSERVATION,
    SERVICE_START_CYCLE,
    START_CYCLE_SCHEMA,
)

INTEGRATION_DIR = (
    Path(__file__).resolve().parents[2] / "custom_components" / "smart_compost"
)

SCHEMAS = {
    SERVICE_LOG_MATERIAL: LOG_MATERIAL_SCHEMA,
    SERVICE_LOG_OBSERVATION: LOG_OBSERVATION_SCHEMA,
    SERVICE_LOG_INTERVENTION: LOG_INTERVENTION_SCHEMA,
    SERVICE_START_CYCLE: START_CYCLE_SCHEMA,
    SERVICE_COMPLETE_CYCLE: COMPLETE_CYCLE_SCHEMA,
}


def _load(relative: str) -> dict:
    return json.loads((INTEGRATION_DIR / relative).read_text(encoding="utf-8"))


def test_strings_and_english_translation_are_identical() -> None:
    assert _load("strings.json") == _load("translations/en.json")


def test_every_entity_and_state_is_translated() -> None:
    entities = _load("strings.json")["entity"]["sensor"]
    for description in SENSORS:
        assert description.translation_key is not None
        entry = entities[description.translation_key]
        assert entry["name"]
        if description.enum_type is not None:
            states = entry["state"]
            for member in description.enum_type:
                assert member.value in states, (
                    f"missing state translation for "
                    f"{description.key}.{member.value}"
                )


def test_every_selector_option_is_translated() -> None:
    selectors = _load("strings.json")["selector"]
    expected = {
        "compost_type": CompostType,
        "compost_method": CompostMethod,
        "location": Location,
        "shelter": Shelter,
        "rain_exposure": RainExposure,
        "sun_exposure": SunExposure,
        "notification_category": NotificationCategory,
    }
    for key, enum_cls in expected.items():
        assert set(selectors[key]["options"]) == {
            member.value for member in enum_cls
        }


def test_action_codes_used_by_the_engine_are_translated() -> None:
    states = _load("strings.json")["entity"]["sensor"]["priority_action"][
        "state"
    ]
    for member in ActionCode:
        assert member.value in states
    assert set(states) == {member.value for member in ActionCode}


def test_cycle_stages_are_translated() -> None:
    states = _load("strings.json")["entity"]["sensor"]["cycle_stage"]["state"]
    assert set(states) == {member.value for member in CycleStage}


def _schema_keys(schema) -> set[str]:
    """Field names declared in a voluptuous schema."""
    return {marker.schema for marker in schema.schema}


def test_services_yaml_strings_and_schemas_agree() -> None:
    """UI (services.yaml), validation (schemas) and strings must match."""
    services_yaml = yaml.safe_load(
        (INTEGRATION_DIR / "services.yaml").read_text(encoding="utf-8")
    )
    strings = _load("strings.json")

    assert set(services_yaml) == set(SCHEMAS)
    assert set(strings["services"]) == set(SCHEMAS)

    for name, spec in services_yaml.items():
        yaml_fields = set(spec["fields"])
        assert yaml_fields == _schema_keys(SCHEMAS[name]), name
        assert yaml_fields == set(strings["services"][name]["fields"]), name
        translated = strings["services"][name]
        assert translated["name"] and translated["description"]

        for field in spec["fields"].values():
            selector = field.get("selector", {})
            if "select" in selector and "translation_key" in selector["select"]:
                translation_key = selector["select"]["translation_key"]
                options = set(selector["select"]["options"])
                assert options <= set(
                    strings["selector"][translation_key]["options"]
                ), f"untranslated option in {translation_key}"


def test_service_icons_cover_all_services() -> None:
    icons = _load("icons.json")
    assert set(icons["services"]) == set(SCHEMAS)


def test_options_strings_cover_the_binding_and_notification_fields() -> None:
    options = _load("strings.json")["options"]["step"]["init"]
    assert set(options["data"]) == {
        "temperature_entity",
        "moisture_entity",
        "voc_entity",
        "ammonia_entity",
        "fill_entity",
        "notification_categories",
    }
    assert set(options["data_description"]) == set(options["data"])
    assert "same_sensor" in options["error"]


def test_notification_strings_cover_every_message_key() -> None:
    """Every key the engine can emit is translated — and nothing else."""
    notifications = _load("strings.json")["notification"]
    assert set(notifications) == set(NOTIFICATION_MESSAGE_KEYS)
    allowed = {"bin", "confidence", "before", "after", "action", "category"}
    for key, entry in notifications.items():
        assert entry["title"], key
        assert entry["message"], key
        for value in (entry["title"], entry["message"]):
            fields = {
                field
                for _, field, _, _ in string.Formatter().parse(value)
                if field
            }
            assert fields <= allowed, f"{key}: unexpected placeholders {fields}"
