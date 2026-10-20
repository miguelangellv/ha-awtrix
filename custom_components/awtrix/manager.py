"""Publish the extra entities of AWTRIX NG devices and report commands the firmware refuses."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.components import mqtt
from homeassistant.core import CALLBACK_TYPE, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.event import async_call_later

from .const import FLAVOR_NG
from .devices import find_prefix, ng_devices
from .discovery import CAPABILITIES_TOPIC, DEFAULT_DISCOVERY_PREFIX, build_entities, encode, overlays_from_capabilities
from .results import EVENT_COMMAND_FAILED, describe, is_benign, parse_failure, result_topics

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

RETRY_SECONDS = 60
MAX_RETRIES = 10


class NgManager:
    """Per AWTRIX NG device: discovery documents, the capabilities subscription and the reply subscriptions."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass
        self._unsubs: dict[str, list[CALLBACK_TYPE]] = {}
        self._overlays: dict[str, list[str] | None] = {}
        self._cancel_retry: CALLBACK_TYPE | None = None
        self._unsub_registry: CALLBACK_TYPE | None = None
        self._retries = 0

    async def async_start(self) -> None:
        """Publish for every NG device known now; retry for the ones whose prefix has not arrived yet."""
        if not await mqtt.async_wait_for_mqtt_client(self._hass):
            _LOGGER.warning("MQTT is not available; the extra AWTRIX NG entities are not published")
            return
        self._unsub_registry = self._hass.bus.async_listen(dr.EVENT_DEVICE_REGISTRY_UPDATED, self._on_device_registry)
        await self.async_sync()

    @callback
    def _on_device_registry(self, event) -> None:
        """A new device may be an AWTRIX NG; look again shortly, once its prefix entity has a state."""
        if event.data.get("action") != "create" or self._cancel_retry is not None:
            return
        self._retries = 0
        self._cancel_retry = async_call_later(self._hass, 10, self.async_sync)

    async def async_sync(self, *_) -> None:
        self._cancel_retry = None
        pending = False
        for device_id, uid, name in ng_devices(self._hass):
            if uid in self._unsubs:
                continue
            found = find_prefix(self._hass, device_id)
            if found is None or found[0] != FLAVOR_NG:
                pending = True
                continue
            await self._async_setup_device(uid, found[1], name)

        if pending and self._retries < MAX_RETRIES:
            self._retries += 1
            self._cancel_retry = async_call_later(self._hass, RETRY_SECONDS, self.async_sync)

    async def _async_setup_device(self, uid: str, prefix: str, name: str | None) -> None:
        unsubs: list[CALLBACK_TYPE] = []
        self._unsubs[uid] = unsubs
        self._overlays[uid] = None

        await self._async_publish_discovery(uid, prefix, name)

        @callback
        def on_capabilities(message) -> None:
            overlays = overlays_from_capabilities(message.payload)
            if overlays and overlays != self._overlays[uid]:
                self._overlays[uid] = overlays
                self._hass.async_create_task(self._async_publish_discovery(uid, prefix, name))

        @callback
        def on_result(message) -> None:
            failure = parse_failure(prefix, message.topic, message.payload)
            if failure is None:
                return
            if is_benign(failure):
                _LOGGER.debug("AWTRIX NG %s: %s", prefix, describe(failure))
                return
            _LOGGER.warning("AWTRIX NG %s: %s", prefix, describe(failure))
            self._hass.bus.async_fire(EVENT_COMMAND_FAILED, {"prefix": prefix, **failure})

        unsubs.append(await mqtt.async_subscribe(self._hass, f"{prefix}/{CAPABILITIES_TOPIC}", on_capabilities))
        for topic in result_topics(prefix):
            unsubs.append(await mqtt.async_subscribe(self._hass, topic, on_result))

    async def _async_publish_discovery(self, uid: str, prefix: str, name: str | None) -> None:
        for topic, config in build_entities(prefix, uid, self._overlays.get(uid), self._discovery_prefix(), name):
            await mqtt.async_publish(self._hass, topic, encode(config), retain=True)

    def _discovery_prefix(self) -> str:
        for entry in self._hass.config_entries.async_entries("mqtt"):
            value = entry.data.get("discovery_prefix") or entry.options.get("discovery_prefix")
            if value:
                return value
        return DEFAULT_DISCOVERY_PREFIX

    @callback
    def async_stop(self) -> None:
        if self._unsub_registry is not None:
            self._unsub_registry()
            self._unsub_registry = None
        if self._cancel_retry is not None:
            self._cancel_retry()
            self._cancel_retry = None
        for unsubs in self._unsubs.values():
            for unsub in unsubs:
                unsub()
        self._unsubs.clear()
