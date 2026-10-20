"""Find Awtrix devices in Home Assistant and read their MQTT topic prefix."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.entity_registry import async_entries_for_device, async_get

from .const import FLAVOR_NG, FLAVOR_V3

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

MANUFACTURER = "Blueforcer"

# Entity of the device whose state holds the MQTT topic prefix.
PREFIX_ENTITY_V3 = "Device topic"
PREFIX_ENTITY_NG = "MQTT prefix"


def is_ng_model(model: str | None) -> bool:
    """AWTRIX NG devices report the model ``AWTRIX NG``; Awtrix 3 reports ``AWTRIX 3``."""
    return "ng" in (model or "").lower().split()


def find_prefix(hass: HomeAssistant, device_id: str) -> tuple[str, str] | None:
    """Return ``(flavor, topic prefix)`` for a device, or ``None`` while the prefix is not known yet."""
    device = dr.async_get(hass).async_get(device_id)
    is_ng = device is not None and is_ng_model(device.model)

    for entity in async_entries_for_device(async_get(hass), device_id, True):
        if entity.original_name == PREFIX_ENTITY_NG:
            is_ng = True
        elif entity.original_name != PREFIX_ENTITY_V3:
            continue
        state = hass.states.get(entity.entity_id)
        if state is not None and state.state not in ("", STATE_UNKNOWN, STATE_UNAVAILABLE):
            return (FLAVOR_NG if is_ng else FLAVOR_V3), state.state
    return None


def ng_devices(hass: HomeAssistant) -> list[tuple[str, str, str | None]]:
    """Return ``(device id, uid, name)`` of every AWTRIX NG device; ``uid`` is the MQTT discovery identifier."""
    found = []
    registry = dr.async_get(hass)
    for item in registry.devices:
        # Current Home Assistant yields the entries; older versions yield the ids.
        device = registry.async_get(item) if isinstance(item, str) else item
        if device is None or device.manufacturer != MANUFACTURER or not is_ng_model(device.model):
            continue
        uid = next((ident[1] for ident in device.identifiers if ident[0] == "mqtt"), None)
        if uid:
            found.append((device.id, uid, device.name))
    return found
