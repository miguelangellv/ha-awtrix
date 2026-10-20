"""MQTT discovery documents for the extra AWTRIX NG entities.

The firmware publishes its own Home Assistant discovery document (matrix and indicator lights, a few selects,
buttons and sensors). The documents built here add what that one leaves out: a weather overlay select, a
moodlight light, volume numbers, clock switches and diagnostic sensors fed from the firmware's retained
``state/device`` and ``state/settings`` topics.

They are single-component documents on the discovery topics, attached to the firmware's device through its
identifier, so Home Assistant shows them on the same device and they keep working without this integration.
Nothing here polls: state comes from topics the firmware already publishes, and the clock only receives a
message when someone changes an entity.

Pure Python, no Home Assistant imports.
"""

from __future__ import annotations

import json
from typing import Any

DEFAULT_DISCOVERY_PREFIX = "homeassistant"

# Used until the firmware's own list arrives on <prefix>/state/capabilities.
DEFAULT_OVERLAYS = ["drizzle", "frost", "rain", "snow", "storm", "thunder"]
OVERLAY_NONE = "none"

_SEPARATOR_MODES = ["steady", "blink", "pulse"]
_TRANSITION_DIRECTIONS = ["normal", "reverse"]

SETTINGS_TOPIC = "state/settings"
DEVICE_TOPIC = "state/device"
CAPABILITIES_TOPIC = "state/capabilities"


def _onoff(key: str) -> str:
    return "{{ 'ON' if value_json." + key + " else 'OFF' }}"


def _set_settings(key: str, value_expr: str) -> str:
    return '{"' + key + '": ' + value_expr + "}"


def build_entities(
    prefix: str,
    uid: str,
    overlays: list[str] | None = None,
    discovery_prefix: str = DEFAULT_DISCOVERY_PREFIX,
    device_name: str | None = None,
) -> list[tuple[str, dict[str, Any]]]:
    """Return ``(discovery topic, config)`` pairs for every extra entity of one AWTRIX NG device."""
    overlay_options = [OVERLAY_NONE] + [o for o in (overlays or DEFAULT_OVERLAYS) if o]

    # Home Assistant wants the device name in every document that shares a device; it is the name the
    # firmware's own document already gave the device.
    device: dict[str, Any] = {"identifiers": [uid]}
    if device_name:
        device["name"] = device_name

    common: dict[str, Any] = {
        "availability_topic": f"{prefix}/availability",
        "device": device,
        "origin": {"name": "ha-awtrix"},
    }
    settings_state = {"state_topic": f"{prefix}/{SETTINGS_TOPIC}"}
    device_state = {"state_topic": f"{prefix}/{DEVICE_TOPIC}"}
    settings_cmd = f"{prefix}/cmd/settings"

    entities: list[tuple[str, str, dict[str, Any]]] = []

    def add(component: str, key: str, config: dict[str, Any]) -> None:
        entities.append((component, key, config))

    # --- Controls --------------------------------------------------------------------------------
    add(
        "select",
        "overlay",
        {
            "name": "Weather overlay",
            "icon": "mdi:weather-pouring",
            "options": overlay_options,
            "command_topic": f"{prefix}/cmd/display",
            "command_template": (
                "{% if value == '" + OVERLAY_NONE + '\' %}{"overlay": null}{% else %}{"overlay": "{{ value }}"}{% endif %}'
            ),
            # The firmware reports no overlay state, so the entity shows what was last sent.
            "optimistic": True,
        },
    )
    add(
        "light",
        "moodlight",
        {
            "name": "Moodlight",
            "schema": "template",
            "icon": "mdi:led-strip-variant",
            "supported_color_modes": ["rgb"],
            "command_topic": f"{prefix}/cmd/display/moodlight",
            "command_on_template": (
                '{"color": "#{{ \'%02x%02x%02x\' % ((red | default(255)) | int, (green | default(255)) | int, (blue | default(255)) | int) }}",'
                ' "brightness": {{ (brightness | default(120)) | int }}}'
            ),
            # An empty payload turns the moodlight off.
            "command_off_template": "",
            "optimistic": True,
        },
    )
    for key, label, enabled in (
        ("buzzerVolume", "Buzzer volume", False),
        ("dfplayerVolume", "DFPlayer volume", False),
        ("mp3Volume", "MP3 volume", False),
    ):
        add(
            "number",
            key,
            {
                "name": label,
                "icon": "mdi:volume-high",
                "min": 0,
                "max": 100,
                "step": 1,
                "mode": "slider",
                "unit_of_measurement": "%",
                "entity_category": "config",
                "enabled_by_default": enabled,
                "command_topic": settings_cmd,
                "command_template": _set_settings(key, "{{ value | int }}"),
                "value_template": "{{ value_json." + key + " }}",
                **settings_state,
            },
        )
    add(
        "number",
        "saturation",
        {
            "name": "Saturation",
            "icon": "mdi:palette",
            "min": 0,
            "max": 100,
            "step": 1,
            "mode": "slider",
            "unit_of_measurement": "%",
            "entity_category": "config",
            "command_topic": settings_cmd,
            "command_template": _set_settings("saturation", "{{ value | int }}"),
            "value_template": "{{ value_json.saturation }}",
            **settings_state,
        },
    )
    add(
        "number",
        "appDurationMs",
        {
            "name": "App duration",
            "icon": "mdi:timer-outline",
            "min": 1000,
            "max": 60000,
            "step": 500,
            "mode": "box",
            "unit_of_measurement": "ms",
            "entity_category": "config",
            "command_topic": settings_cmd,
            "command_template": _set_settings("appDurationMs", "{{ value | int }}"),
            "value_template": "{{ value_json.appDurationMs }}",
            **settings_state,
        },
    )
    for key, label, icon in (
        ("time24h", "24-hour clock", "mdi:clock-time-twelve-outline"),
        ("timeShowSeconds", "Show seconds", "mdi:timer-sand"),
        ("useCelsius", "Celsius", "mdi:temperature-celsius"),
        ("uppercase", "Uppercase text", "mdi:format-letter-case-upper"),
        ("blockNavigation", "Block buttons", "mdi:gesture-tap-button"),
    ):
        add(
            "switch",
            key,
            {
                "name": label,
                "icon": icon,
                "entity_category": "config",
                "command_topic": settings_cmd,
                "command_template": _set_settings(key, "{{ 'true' if value == 'ON' else 'false' }}"),
                "value_template": _onoff(key),
                "state_on": "ON",
                "state_off": "OFF",
                **settings_state,
            },
        )
    for key, label, options in (
        ("timeSeparatorMode", "Clock separator", _SEPARATOR_MODES),
        ("transitionDirection", "Transition direction", _TRANSITION_DIRECTIONS),
    ):
        add(
            "select",
            key,
            {
                "name": label,
                "entity_category": "config",
                "options": options,
                "command_topic": settings_cmd,
                "command_template": _set_settings(key, '"{{ value }}"'),
                "value_template": "{{ value_json." + key + " }}",
                **settings_state,
            },
        )

    # --- Diagnostics from the retained device state ----------------------------------------------
    diag = {"entity_category": "diagnostic", **device_state}
    add(
        "sensor",
        "minFreeHeap",
        {
            "name": "Lowest free heap",
            "icon": "mdi:memory",
            "device_class": "data_size",
            "unit_of_measurement": "B",
            "suggested_unit_of_measurement": "kB",
            "state_class": "measurement",
            "value_template": "{{ value_json.minFreeHeapBytes }}",
            **diag,
        },
    )
    add(
        "sensor",
        "largestFreeBlock",
        {
            "name": "Largest free heap block",
            "icon": "mdi:memory",
            "device_class": "data_size",
            "unit_of_measurement": "B",
            "suggested_unit_of_measurement": "kB",
            "state_class": "measurement",
            "value_template": "{{ value_json.largestFreeBlockBytes }}",
            **diag,
        },
    )
    add(
        "sensor",
        "resetReason",
        {"name": "Last reset reason", "icon": "mdi:restart-alert", "value_template": "{{ value_json.resetReason }}", **diag},
    )
    add(
        "sensor",
        "mqttConnects",
        {
            "name": "MQTT connects",
            "icon": "mdi:lan-connect",
            "state_class": "total_increasing",
            "value_template": "{{ value_json.mqtt.connects }}",
            **diag,
        },
    )
    add(
        "sensor",
        "mqttLastError",
        {
            "name": "MQTT last error",
            "icon": "mdi:lan-disconnect",
            "value_template": "{{ value_json.mqtt.lastError | default('none', true) }}",
            **diag,
        },
    )
    add(
        "sensor",
        "fps",
        {
            "name": "Frame rate",
            "icon": "mdi:speedometer",
            "unit_of_measurement": "fps",
            "state_class": "measurement",
            "enabled_by_default": False,
            "value_template": "{{ value_json.fps }}",
            **diag,
        },
    )
    add(
        "sensor",
        "messageCount",
        {
            "name": "Commands received",
            "icon": "mdi:counter",
            "state_class": "total_increasing",
            "enabled_by_default": False,
            "value_template": "{{ value_json.messageCount }}",
            **diag,
        },
    )
    add(
        "sensor",
        "psramFree",
        {
            "name": "Free PSRAM",
            "icon": "mdi:memory",
            "device_class": "data_size",
            "unit_of_measurement": "B",
            "suggested_unit_of_measurement": "kB",
            "state_class": "measurement",
            "enabled_by_default": False,
            "value_template": "{{ value_json.psramFreeBytes | default(none) }}",
            **diag,
        },
    )

    out = []
    for component, key, config in entities:
        config = {**config, **common, "unique_id": f"{uid}_ext_{key}"}
        out.append((f"{discovery_prefix}/{component}/{uid}/ext_{key}/config", config))
    return out


def encode(config: dict[str, Any]) -> str:
    """Serialise a discovery config the way it is published."""
    return json.dumps(config, sort_keys=True)


def overlays_from_capabilities(payload: str | bytes | None) -> list[str] | None:
    """Pull the overlay names out of ``<prefix>/state/capabilities``; ``None`` if absent or unusable."""
    if not payload:
        return None
    try:
        data = json.loads(payload)
    except (TypeError, ValueError):
        return None
    overlays = data.get("overlays") if isinstance(data, dict) else None
    if isinstance(overlays, list) and all(isinstance(o, str) for o in overlays) and overlays:
        return [o for o in overlays if o]
    return None
