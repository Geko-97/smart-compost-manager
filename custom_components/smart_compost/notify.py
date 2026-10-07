"""Home Assistant glue for M6 events and notifications (docs/16 §8).

Two channels, both supported by design:

* the **bus** (`smart_compost_event`, `smart_compost_notification`) always
  fires with machine-readable payloads — that is the custom-automation
  channel, where the user decides conditions and actions;
* **built-in** persistent notifications render translated text and respect
  the per-category opt-in from the options flow (docs/14 §10).

Text never lives in code: titles and messages come from strings.json's
`notification` section at runtime (docs/01 PR-025 localization).
"""

from __future__ import annotations

import logging
import string
from collections.abc import Mapping
from typing import Any

from homeassistant.components import persistent_notification
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.translation import async_get_translations

from .const import (
    CONF_NOTIFICATION_CATEGORIES,
    DOMAIN,
    EVENT_COMPOST_EVENT,
    EVENT_COMPOST_NOTIFICATION,
)
from .core.events import CompostEvent
from .core.model import ActionCode
from .core.notifications import NotificationCategory, SentNotification

_LOGGER = logging.getLogger(__name__)

#: Translation categories merged to render one built-in notification.
#: `en` is always the base so a missing language can degrade, not vanish.
_TRANSLATION_CATEGORIES = ("notification", "selector", "entity")

_ALLOWED_PLACEHOLDERS = frozenset(
    {"bin", "confidence", "before", "after", "action", "category"}
)


def read_notification_categories(
    options: Mapping[str, Any],
) -> frozenset[NotificationCategory]:
    """Built-in categories the user opted into.

    An absent option means the default (all categories); an explicit
    empty list means the user turned the built-in channel off entirely.
    Unknown stored codes are ignored with a warning, never re-added.
    """
    raw = options.get(CONF_NOTIFICATION_CATEGORIES)
    if not isinstance(raw, list):
        return frozenset(NotificationCategory)
    parsed: set[NotificationCategory] = set()
    for item in raw:
        try:
            parsed.add(NotificationCategory(item))
        except ValueError:
            _LOGGER.warning("Ignoring unknown notification category %r", item)
    return frozenset(parsed)


def event_payload(event: CompostEvent) -> dict[str, Any]:
    """docs/10 §4 metadata, machine-readable only."""
    return {
        "timestamp": event.timestamp.isoformat(),
        "bin_id": event.bin_id,
        "cycle_id": event.cycle_id,
        "type": event.type.value,
        "source": event.origin.value,
        "before_state": event.before_state,
        "after_state": event.after_state,
        "reason": event.reason,
        "notes": event.notes,
    }


def notification_payload(
    bin_id: str | None, note: SentNotification
) -> dict[str, Any]:
    """docs/16 §5 content as codes: what/why/action/confidence."""
    return {
        "bin_id": bin_id,
        "timestamp": note.emitted_at.isoformat(),
        "category": note.category.value,
        "kind": note.kind.value,
        "severity": note.severity.value,
        "confidence": note.confidence,
        "reasons": list(note.reasons),
        "action": note.action.value,
        "before_state": note.before,
        "after_state": note.after,
    }


@callback
def async_fire_event(hass: HomeAssistant, event: CompostEvent) -> None:
    """Publish one domain event on the bus (custom-automation channel)."""
    hass.bus.async_fire(EVENT_COMPOST_EVENT, event_payload(event))


@callback
def async_fire_notification(
    hass: HomeAssistant, bin_id: str | None, note: SentNotification
) -> None:
    """Publish one engine decision on the bus, always — even when the
    built-in channel is disabled for this category (docs/16 §8)."""
    hass.bus.async_fire(
        EVENT_COMPOST_NOTIFICATION, notification_payload(bin_id, note)
    )


async def async_show_notification(
    hass: HomeAssistant,
    entry: ConfigEntry,
    note: SentNotification,
    enabled: frozenset[NotificationCategory],
) -> None:
    """Create or update the built-in persistent notification for one bin.

    The stable notification id means an update replaces the previous
    message and a recovery replaces the issue — one card per category,
    never an accumulating pile (docs/16 §4 deduplication).
    """
    if note.category not in enabled:
        return

    translations = await _async_translations(hass)
    prefix = f"component.smart_compost.notification.{note.message_key}"
    title = translations.get(f"{prefix}.title")
    template = translations.get(f"{prefix}.message")
    if title is None or template is None:
        _LOGGER.warning(
            "Missing notification translation for %r; skipping built-in"
            " notification (the bus payload was still fired)",
            note.message_key,
        )
        return

    action_label = ""
    if note.action is not ActionCode.NONE:
        action_label = translations.get(
            "component.smart_compost.entity.sensor.priority_action.state"
            f".{note.action.value}",
            "",
        )
    category_label = translations.get(
        "component.smart_compost.selector.notification_category.options"
        f".{note.category.value}",
        note.category.value,
    )

    values = {
        "bin": entry.title,
        "confidence": note.confidence,
        "before": note.before or "",
        "after": note.after or "",
        "action": action_label,
        "category": category_label,
    }
    try:
        message = _safe_format(template, values)
        rendered_title = _safe_format(title, values)
    except ValueError:
        # A hand-edited translation must not break the assessment pipeline;
        # the parity test keeps the shipped strings consistent.
        _LOGGER.warning(
            "Invalid placeholders in notification translation %r;"
            " skipping built-in notification",
            note.message_key,
        )
        return

    persistent_notification.async_create(
        hass,
        message,
        title=rendered_title,
        notification_id=f"{DOMAIN}_{entry.entry_id}_{note.category.value}",
    )


def _safe_format(template: str, values: dict[str, Any]) -> str:
    """Render a translated template, rejecting unknown placeholders."""
    used = {
        field_name
        for _, field_name, _, _ in string.Formatter().parse(template)
        if field_name
    }
    if not used <= _ALLOWED_PLACEHOLDERS:
        raise ValueError(f"unexpected placeholders: {sorted(used)}")
    return template.format(**values)


async def _async_translations(hass: HomeAssistant) -> dict[str, str]:
    """Merged translations: `en` as the base, configured language on top."""
    merged: dict[str, str] = {}
    languages = dict.fromkeys(["en", hass.config.language])
    for language in languages:
        for category in _TRANSLATION_CATEGORIES:
            merged.update(
                await async_get_translations(
                    hass, language, category, integrations=[DOMAIN]
                )
            )
    return merged
