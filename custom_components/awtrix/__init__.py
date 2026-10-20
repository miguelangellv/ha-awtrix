"""Awtrix."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.components import mqtt
from homeassistant.const import Platform
from homeassistant.exceptions import ServiceValidationError
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.start import async_at_started

from .const import DOMAIN
from .devices import find_prefix
from .manager import NgManager
from .messages import HANDLERS, UnsupportedError, build

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant, ServiceCall

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, _: dict):
    """Awtrix integration setup."""

    def make_handler(action: str):
        async def handler(call: ServiceCall) -> None:
            flavor, prefix = _resolve_device(hass, call.data.get("device"))
            data = dict(call.data)
            try:
                messages = build(action, flavor, prefix, data)
            except UnsupportedError as err:
                raise ServiceValidationError(str(err)) from err
            except (KeyError, ValueError, TypeError) as err:
                raise ServiceValidationError(f"Invalid data for awtrix.{action}: {err}") from err

            for message in messages:
                await mqtt.async_publish(hass, message.topic, message.payload)

        return handler

    for action in HANDLERS:
        hass.services.async_register(DOMAIN, action, make_handler(action))

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Start publishing the extra AWTRIX NG entities and watching command results."""
    manager = NgManager(hass)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = manager

    async def start(_: HomeAssistant) -> None:
        await manager.async_start()

    entry.async_on_unload(async_at_started(hass, start))
    entry.async_on_unload(manager.async_stop)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Stop the manager; discovery documents stay retained on the broker so the entities keep working."""
    hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    return True


def _resolve_device(hass: HomeAssistant, device_id: str | None) -> tuple[str, str]:
    """Return ``(flavor, topic prefix)`` for a device, raising a user-facing error if it cannot be resolved."""
    if not device_id:
        raise ServiceValidationError("An Awtrix device is required")

    found = find_prefix(hass, device_id)
    if found is None:
        raise ServiceValidationError("Could not find the MQTT topic of this Awtrix device; is the device connected to MQTT?")
    return found


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate old config entries."""
    version = entry.version
    if version < 2:
        if entry.title == "Atriwx":
            hass.config_entries.async_update_entry(entry, title="Awtrix", version=2)

    return True
