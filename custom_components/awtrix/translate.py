"""Translate Awtrix 3 payload vocabulary into the AWTRIX NG one.

The actions of this integration were written against the Awtrix 3 MQTT API. AWTRIX NG accepts the same kind
of JSON but names most keys differently (``color`` -> ``textColor``, ``duration`` in seconds -> ``durationMs``,
draw commands as arrays, ...). Every function here is pure so it can be tested without Home Assistant.

Keys that are not part of the Awtrix 3 vocabulary are passed through untouched, which is how NG-only options
(``overlay``, ``palette``, ``effectSpeed``, ``brightness``, ...) reach the device.
"""

from __future__ import annotations

from typing import Any

NG_TRANSITIONS = [
    "Random",
    "Slide",
    "Dim",
    "Zoom",
    "Rotate",
    "Pixelate",
    "Curtain",
    "Ripple",
    "Blink",
    "Reload",
    "Fade",
]

_ICON_MODES = {0: "fixed", 1: "pushOnce", 2: "push"}
_TEXT_CASES = {0: "inherit", 1: "upper", 2: "asTyped"}
_LIFETIME_MODES = {0: "remove", 1: "mark"}

# Awtrix 3 draw command -> NG command name.
_DRAW_COMMANDS = {
    "dp": "pixel",
    "dl": "line",
    "dr": "rect",
    "df": "rectFill",
    "dc": "circle",
    "dfc": "circleFill",
    "dt": "text",
    "db": "bitmap",
}

# Awtrix 3 app/notification key -> NG key, for keys whose value needs no conversion.
_APP_RENAMES = {
    "color": "textColor",
    "background": "backgroundColor",
    "progressC": "progressColor",
    "progressBC": "progressTrackColor",
    "bar": "barChart",
    "line": "lineChart",
    "autoscale": "chartAutoscale",
    "lineC": "chartColor",
    "blinkText": "textBlinkMs",
    "fadeText": "textFadeMs",
    "center": "textCenter",
    "textOffset": "textOffsetX",
    "rtttl": "soundRtttl",
    "loopSound": "soundLoop",
}

# Awtrix 3 keys with no NG equivalent.
_APP_DROPPED = {"save", "pos", "clients", "topText", "barBC", "rainbow", "gradient", "effectSettings"}

# Awtrix 3 settings key -> NG settings key, for keys whose value needs no conversion.
_SETTINGS_RENAMES = {
    "TSPEED": "transitionDurationMs",
    "TCOL": "textColor",
    "CHCOL": "calendarHeaderColor",
    "CBCOL": "calendarBodyColor",
    "CTCOL": "calendarTextColor",
    "BRI": "brightness",
    "ABRI": "autoBrightness",
    "ATRANS": "autoTransition",
    "CCORRECTION": "colorCorrection",
    "CTEMP": "colorTint",
    "CEL": "useCelsius",
    "BLOCKN": "blockNavigation",
    "UPPERCASE": "uppercase",
    "TIME_COL": "timeColor",
    "DATE_COL": "dateColor",
    "TEMP_COL": "temperatureColor",
    "HUM_COL": "humidityColor",
    "BAT_COL": "batteryColor",
}

# Nested NG objects: v3 key -> (object, key).
_SETTINGS_NESTED = {
    "SSPEED": ("scroll", "speed"),
    "WD": ("weekdayBar", "show"),
    "WDCA": ("weekdayBar", "activeColor"),
    "WDCI": ("weekdayBar", "inactiveColor"),
    "SOM": ("weekdayBar", "startOnMonday"),
}

# Awtrix 3 settings keys that have no NG equivalent; reported back to the caller.
_SETTINGS_UNSUPPORTED = {"TMODE", "DFORMAT", "TIM", "DAT", "HUM", "TEMP", "BAT"}


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _seconds_to_ms(value: Any) -> int:
    return int(float(value) * 1000)


def _translate_fragments(text: list) -> list:
    out = []
    for fragment in text:
        if isinstance(fragment, dict):
            fragment = dict(fragment)
            if "t" in fragment:
                fragment["text"] = fragment.pop("t")
            if "c" in fragment:
                fragment["color"] = fragment.pop("c")
        out.append(fragment)
    return out


def _translate_draw(draw: Any) -> Any:
    """Turn ``[{"dp": [x, y, c]}, ...]`` into ``[["pixel", x, y, c], ...]``."""
    if not isinstance(draw, list):
        return draw
    out = []
    for item in draw:
        if isinstance(item, dict):
            for command, args in item.items():
                name = _DRAW_COMMANDS.get(command)
                if name is not None and isinstance(args, list):
                    out.append([name, *args])
        else:
            # Already NG style (array with the command name first).
            out.append(item)
    return out


def translate_app_payload(data: dict[str, Any]) -> dict[str, Any]:
    """Convert an Awtrix 3 app or notification payload into an AWTRIX NG one."""
    out: dict[str, Any] = {}

    for key, value in data.items():
        if key in _APP_DROPPED:
            continue
        if key in _APP_RENAMES:
            out[_APP_RENAMES[key]] = value
        elif key == "text" and isinstance(value, list):
            out["text"] = _translate_fragments(value)
        elif key == "draw":
            out["draw"] = _translate_draw(value)
        elif key == "overlay":
            overlay = normalise_overlay(value)
            if overlay is not None:
                out["overlay"] = overlay
        elif key in ("duration", "lifetime"):
            out["durationMs" if key == "duration" else "lifetimeMs"] = _seconds_to_ms(value)
        elif key == "lifetimeMode":
            out["lifetimeExpiry"] = _LIFETIME_MODES.get(int(value), "remove")
        elif key == "pushIcon":
            out["iconMode"] = _ICON_MODES.get(int(value), "fixed")
        elif key == "textCase":
            out["textCase"] = _TEXT_CASES.get(value, value) if isinstance(value, int) else value
        elif key == "noScroll":
            if value:
                out.setdefault("scroll", {})["mode"] = "static"
        elif key == "scrollSpeed":
            out.setdefault("scroll", {})["speed"] = int(value)
        else:
            out[key] = value

    # Awtrix 3 colour effects map onto NG palettes painted onto the text.
    if data.get("rainbow"):
        out["textColor"] = "palette"
        out.setdefault("palette", "Rainbow")
    gradient = data.get("gradient")
    if isinstance(gradient, list) and len(gradient) >= 2:
        out["textColor"] = "palette"
        out.setdefault("palette", gradient)

    settings = data.get("effectSettings")
    if isinstance(settings, dict):
        if "speed" in settings:
            out.setdefault("effectSpeed", _clamp(float(settings["speed"]), 0.1, 10.0))
        if "palette" in settings:
            out.setdefault("palette", settings["palette"])
        if "blend" in settings:
            out.setdefault("paletteBlend", bool(settings["blend"]))

    return out


def translate_settings(data: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    """Convert Awtrix 3 settings into AWTRIX NG ones.

    Returns ``(settings, display, unsupported)``: the body for ``cmd/settings``, the body for ``cmd/display``
    (matrix power and global overlay live there in NG) and the Awtrix 3 keys that have no NG counterpart.
    """
    settings: dict[str, Any] = {}
    display: dict[str, Any] = {}
    unsupported: list[str] = []

    for key, value in data.items():
        if key in _SETTINGS_RENAMES:
            settings[_SETTINGS_RENAMES[key]] = value
        elif key in _SETTINGS_NESTED:
            parent, child = _SETTINGS_NESTED[key]
            settings.setdefault(parent, {})[child] = int(value) if key == "SSPEED" else value
        elif key == "ATIME":
            settings["appDurationMs"] = _seconds_to_ms(value)
        elif key == "TEFF":
            index = int(value)
            if 0 <= index < len(NG_TRANSITIONS):
                settings["transitionEffect"] = NG_TRANSITIONS[index]
            else:
                unsupported.append(key)
        elif key == "TFORMAT":
            fmt = str(value)
            settings["time24h"] = "hh" not in fmt
            settings["timeShowSeconds"] = "ss" in fmt
        elif key == "VOL":
            # Awtrix 3 volume is 0-30, NG volumes are percent.
            percent = int(_clamp(float(value) * 100 / 30, 0, 100))
            settings["buzzerVolume"] = percent
            settings["dfplayerVolume"] = percent
        elif key == "MATP":
            display["power"] = bool(value)
        elif key == "OVERLAY":
            display["overlay"] = normalise_overlay(value)
        elif key in _SETTINGS_UNSUPPORTED:
            unsupported.append(key)
        else:
            # Not an Awtrix 3 key: assume it is already an NG setting.
            settings[key] = value

    return settings, display, unsupported


def normalise_overlay(value: Any) -> str | None:
    """``clear``/``none``/empty mean "no overlay" in both firmwares; NG wants ``null``."""
    if value is None:
        return None
    name = str(value).strip()
    if name.lower() in ("", "clear", "none", "off"):
        return None
    return name
