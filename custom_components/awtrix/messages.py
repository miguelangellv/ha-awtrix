"""Build the MQTT messages for every action, for both firmware flavours.

Pure Python (no Home Assistant imports) so the topic and payload logic can be unit tested on its own.

Awtrix 3 listens on ``<prefix>/<command>``; AWTRIX NG listens on ``<prefix>/cmd/<command>`` with a different
command layout and key names. ``build`` returns the list of messages one action turns into.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import json
import re
from typing import Any

from .const import FLAVOR_NG, FLAVOR_V3
from .translate import normalise_overlay, translate_app_payload, translate_settings

NG_APP_NAME = re.compile(r"^[A-Za-z0-9_-]{1,32}$")
NG_AUDIO_KEYS = ("sound", "mp3", "melody", "track", "rtttl", "station", "index", "url")

# Fields that are always strings on the wire, even when Home Assistant hands us a number.
_TO_STRING = ("text", "icon", "color", "background", "progressC", "progressBC", "barBC", "lineC", "effect", "overlay", "sound", "rtttl")


class UnsupportedError(ValueError):
    """The action does not exist on this firmware flavour."""


@dataclass(frozen=True)
class Message:
    """One MQTT publish."""

    topic: str
    payload: str


def _json(data: Any) -> str:
    return json.dumps(data)


def _strip(data: dict[str, Any], *extra: str) -> dict[str, Any]:
    """Drop the fields that address the device or action rather than belong in the payload."""
    return {k: v for k, v in data.items() if k not in ("device", *extra) and v is not None}


def _stringify(payload: dict[str, Any]) -> dict[str, Any]:
    for key in _TO_STRING:
        if isinstance(payload.get(key), (int, float)) and not isinstance(payload[key], bool):
            payload[key] = str(payload[key])
    if isinstance(payload.get("text"), list):
        for fragment in payload["text"]:
            if isinstance(fragment, dict) and isinstance(fragment.get("t"), (int, float)):
                fragment["t"] = str(fragment["t"])
    return payload


def _topic(flavor: str, prefix: str, v3: str, ng: str) -> str:
    return f"{prefix}/{v3 if flavor == FLAVOR_V3 else 'cmd/' + ng}"


def _ng_only(flavor: str, action: str) -> None:
    if flavor != FLAVOR_NG:
        raise UnsupportedError(f"'{action}' is only supported by AWTRIX NG devices")


def _v3_only(flavor: str, action: str) -> None:
    if flavor != FLAVOR_V3:
        raise UnsupportedError(f"'{action}' is only supported by Awtrix 3 devices")


def _check_ng_app(app: str) -> None:
    if not NG_APP_NAME.match(str(app)):
        raise ValueError("App name must match [A-Za-z0-9_-]{1,32} on AWTRIX NG")


# --- Existing actions ---------------------------------------------------------------------------------


def settings(flavor: str, prefix: str, data: dict[str, Any]) -> list[Message]:
    payload = _strip(data)
    if flavor == FLAVOR_V3:
        return [Message(f"{prefix}/settings", _json(_stringify(payload)))]

    body, display, _ = translate_settings(payload)
    messages = []
    if body:
        messages.append(Message(f"{prefix}/cmd/settings", _json(body)))
    if display:
        messages.append(Message(f"{prefix}/cmd/display", _json(display)))
    return messages


def dismiss(flavor: str, prefix: str, data: dict[str, Any]) -> list[Message]:
    name = data.get("name")
    if flavor == FLAVOR_V3:
        return [Message(f"{prefix}/notify/dismiss", "")]
    suffix = f"/{name}" if name else ""
    return [Message(f"{prefix}/cmd/notify/dismiss{suffix}", "")]


def notification(flavor: str, prefix: str, data: dict[str, Any]) -> list[Message]:
    payload = _strip(data, "app")
    if flavor == FLAVOR_V3:
        return [Message(f"{prefix}/notify", _json(_stringify(payload)))]
    return [Message(f"{prefix}/cmd/notify", _json(translate_app_payload(_stringify(payload))))]


def custom_app(flavor: str, prefix: str, data: dict[str, Any]) -> list[Message]:
    app = data["app"]
    payload = _strip(data, "app")
    if flavor == FLAVOR_V3:
        return [Message(f"{prefix}/custom/{app}", _json(_stringify(payload)))]
    _check_ng_app(app)
    body = translate_app_payload(_stringify(payload))
    if not body:
        # NG treats an empty body as "delete the app".
        raise ValueError("A custom app needs at least one option")
    return [Message(f"{prefix}/cmd/apps/pushed/{app}", _json(body))]


def delete_custom_app(flavor: str, prefix: str, data: dict[str, Any]) -> list[Message]:
    app = data["app"]
    if flavor == FLAVOR_V3:
        return [Message(f"{prefix}/custom/{app}", "")]
    _check_ng_app(app)
    return [Message(f"{prefix}/cmd/apps/pushed/{app}", "")]


def deep_sleep(flavor: str, prefix: str, data: dict[str, Any]) -> list[Message]:
    seconds = data.get("sleep")
    if flavor == FLAVOR_V3:
        return [Message(f"{prefix}/sleep", _json(_strip(data)))]
    if seconds is None:
        raise ValueError("'sleep' (seconds) is required")
    return [Message(f"{prefix}/cmd/device/sleep", _json({"durationMs": int(float(seconds) * 1000)}))]


def switch_app(flavor: str, prefix: str, data: dict[str, Any]) -> list[Message]:
    body: dict[str, Any] = {"name": data["name"]}
    if flavor == FLAVOR_NG and data.get("fast") is not None:
        body["fast"] = bool(data["fast"])
    return [Message(_topic(flavor, prefix, "switch", "apps/switch"), _json(body))]


# --- New actions --------------------------------------------------------------------------------------


def next_app(flavor: str, prefix: str, data: dict[str, Any]) -> list[Message]:
    return [Message(_topic(flavor, prefix, "nextapp", "apps/next"), "")]


def previous_app(flavor: str, prefix: str, data: dict[str, Any]) -> list[Message]:
    return [Message(_topic(flavor, prefix, "previousapp", "apps/previous"), "")]


def power(flavor: str, prefix: str, data: dict[str, Any]) -> list[Message]:
    body = _json({"power": bool(data["power"])})
    return [Message(_topic(flavor, prefix, "power", "display"), body)]


def overlay(flavor: str, prefix: str, data: dict[str, Any]) -> list[Message]:
    name = normalise_overlay(data.get("overlay"))
    if flavor == FLAVOR_V3:
        return [Message(f"{prefix}/settings", _json({"OVERLAY": name or "clear"}))]
    return [Message(f"{prefix}/cmd/display", _json({"overlay": name}))]


def moodlight(flavor: str, prefix: str, data: dict[str, Any]) -> list[Message]:
    topic = _topic(flavor, prefix, "moodlight", "display/moodlight")
    if data.get("enabled") is False:
        return [Message(topic, "")]
    body = _strip(data, "enabled")
    if flavor == FLAVOR_NG:
        body.pop("kelvin", None)
    return [Message(topic, _json(body))]


def indicator(flavor: str, prefix: str, data: dict[str, Any]) -> list[Message]:
    number = int(data["indicator"])
    if number not in (1, 2, 3):
        raise ValueError("indicator must be 1, 2 or 3")
    if flavor == FLAVOR_V3:
        topic = f"{prefix}/indicator{number}"
        if data.get("enabled") is False:
            return [Message(topic, _json({"color": "0"}))]
        body = _strip(data, "indicator", "enabled")
        body = {k: body[k] for k in ("color", "blink", "fade") if k in body}
        return [Message(topic, _json(body))]

    topic = f"{prefix}/cmd/indicators/{number}"
    if data.get("enabled") is False:
        return [Message(topic, "")]
    body = {}
    if "color" in data and data["color"] is not None:
        body["color"] = data["color"]
    if data.get("blink") is not None:
        body["blinkMs"] = int(data["blink"])
    if data.get("fade") is not None:
        body["fadeMs"] = int(data["fade"])
    return [Message(topic, _json(body))]


def play_sound(flavor: str, prefix: str, data: dict[str, Any]) -> list[Message]:
    given = {k: data[k] for k in NG_AUDIO_KEYS if data.get(k) not in (None, "")}
    if len(given) != 1:
        raise ValueError(f"Exactly one of {', '.join(NG_AUDIO_KEYS)} is required")
    key, value = next(iter(given.items()))
    if flavor == FLAVOR_NG:
        if key in ("track", "index"):
            value = int(value)
        return [Message(f"{prefix}/cmd/audio/play", _json({key: value}))]
    if key == "sound":
        return [Message(f"{prefix}/sound", _json({"sound": str(value)}))]
    if key == "rtttl":
        return [Message(f"{prefix}/rtttl", str(value))]
    raise UnsupportedError(f"'{key}' is only supported by AWTRIX NG devices; use 'sound' or 'rtttl'")


def stop_sound(flavor: str, prefix: str, data: dict[str, Any]) -> list[Message]:
    _ng_only(flavor, "stop_sound")
    scope = data.get("scope")
    return [Message(f"{prefix}/cmd/audio/stop", _json({"scope": scope}) if scope else "")]


def reboot(flavor: str, prefix: str, data: dict[str, Any]) -> list[Message]:
    return [Message(_topic(flavor, prefix, "reboot", "device/reboot"), "")]


def update_firmware(flavor: str, prefix: str, data: dict[str, Any]) -> list[Message]:
    _v3_only(flavor, "update_firmware")
    return [Message(f"{prefix}/doupdate", "")]


def app_order(flavor: str, prefix: str, data: dict[str, Any]) -> list[Message]:
    order = list(data.get("order") or [])
    disabled = list(data.get("disabled") or [])
    if flavor == FLAVOR_NG:
        body: dict[str, Any] = {"disabled": disabled}
        if order:
            body["order"] = order
        return [Message(f"{prefix}/cmd/apps/order", _json(body))]
    apps = [{"name": name, "show": True, "pos": pos} for pos, name in enumerate(order)]
    apps += [{"name": name, "show": False} for name in disabled]
    return [Message(f"{prefix}/apps", _json(apps))]


def reset_settings(flavor: str, prefix: str, data: dict[str, Any]) -> list[Message]:
    _ng_only(flavor, "reset_settings")
    return [Message(f"{prefix}/cmd/settings/reset", "")]


def get_screen(flavor: str, prefix: str, data: dict[str, Any]) -> list[Message]:
    _ng_only(flavor, "get_screen")
    return [Message(f"{prefix}/cmd/screen/get", "")]


HANDLERS: dict[str, Callable[[str, str, dict[str, Any]], list[Message]]] = {
    "settings": settings,
    "dismiss": dismiss,
    "notification": notification,
    "custom_app": custom_app,
    "delete_custom_app": delete_custom_app,
    "deep_sleep": deep_sleep,
    "switch_app": switch_app,
    "next_app": next_app,
    "previous_app": previous_app,
    "power": power,
    "overlay": overlay,
    "moodlight": moodlight,
    "indicator": indicator,
    "play_sound": play_sound,
    "stop_sound": stop_sound,
    "reboot": reboot,
    "update_firmware": update_firmware,
    "app_order": app_order,
    "reset_settings": reset_settings,
    "get_screen": get_screen,
}


def build(action: str, flavor: str, prefix: str, data: dict[str, Any]) -> list[Message]:
    """Return the MQTT messages ``action`` turns into for a device of the given flavour."""
    return HANDLERS[action](flavor, prefix, data)
