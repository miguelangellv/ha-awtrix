"""Topic and payload tests for both firmware flavours. Run with ``python -m unittest discover``."""

from __future__ import annotations

import json
import unittest

from tests._load import const, messages

V3, NG = const.FLAVOR_V3, const.FLAVOR_NG
P = "awtrix_test"


def build(action, flavor, **data):
    return messages.build(action, flavor, P, data)


def one(action, flavor, **data):
    (msg,) = build(action, flavor, **data)
    return msg.topic, (json.loads(msg.payload) if msg.payload else msg.payload)


class Awtrix3Tests(unittest.TestCase):
    """The Awtrix 3 behaviour must stay exactly what it was."""

    def test_settings_passthrough(self):
        self.assertEqual(one("settings", V3, device="d", BRI=50), (f"{P}/settings", {"BRI": 50}))

    def test_notification_numeric_text_becomes_string(self):
        topic, body = one("notification", V3, device="d", text=42, color=255, duration=5)
        self.assertEqual(topic, f"{P}/notify")
        self.assertEqual(body, {"text": "42", "color": "255", "duration": 5})

    def test_fragment_numbers_become_strings(self):
        _, body = one("notification", V3, device="d", text=[{"t": 7, "c": "FF0000"}])
        self.assertEqual(body["text"], [{"t": "7", "c": "FF0000"}])

    def test_custom_app_and_delete(self):
        self.assertEqual(one("custom_app", V3, device="d", app="x", text="hi"), (f"{P}/custom/x", {"text": "hi"}))
        self.assertEqual(one("delete_custom_app", V3, device="d", app="x"), (f"{P}/custom/x", ""))

    def test_simple_commands(self):
        self.assertEqual(one("dismiss", V3, device="d"), (f"{P}/notify/dismiss", ""))
        self.assertEqual(one("deep_sleep", V3, device="d", sleep=120), (f"{P}/sleep", {"sleep": 120}))
        self.assertEqual(one("switch_app", V3, device="d", name="Time"), (f"{P}/switch", {"name": "Time"}))
        self.assertEqual(one("next_app", V3, device="d"), (f"{P}/nextapp", ""))
        self.assertEqual(one("previous_app", V3, device="d"), (f"{P}/previousapp", ""))
        self.assertEqual(one("reboot", V3, device="d"), (f"{P}/reboot", ""))
        self.assertEqual(one("update_firmware", V3, device="d"), (f"{P}/doupdate", ""))
        self.assertEqual(one("power", V3, device="d", power=False), (f"{P}/power", {"power": False}))

    def test_overlay_uses_settings(self):
        self.assertEqual(one("overlay", V3, device="d", overlay="rain"), (f"{P}/settings", {"OVERLAY": "rain"}))
        self.assertEqual(one("overlay", V3, device="d", overlay="clear"), (f"{P}/settings", {"OVERLAY": "clear"}))

    def test_indicator(self):
        self.assertEqual(
            one("indicator", V3, device="d", indicator=2, color="#FF0000", blink=500),
            (f"{P}/indicator2", {"color": "#FF0000", "blink": 500}),
        )
        self.assertEqual(one("indicator", V3, device="d", indicator=1, enabled=False), (f"{P}/indicator1", {"color": "0"}))

    def test_moodlight(self):
        self.assertEqual(
            one("moodlight", V3, device="d", kelvin=3000, brightness=50), (f"{P}/moodlight", {"kelvin": 3000, "brightness": 50})
        )
        self.assertEqual(one("moodlight", V3, device="d", enabled=False), (f"{P}/moodlight", ""))

    def test_sound(self):
        self.assertEqual(one("play_sound", V3, device="d", sound="beep"), (f"{P}/sound", {"sound": "beep"}))
        (msg,) = build("play_sound", V3, device="d", rtttl="x:d=4:c")
        self.assertEqual((msg.topic, msg.payload), (f"{P}/rtttl", "x:d=4:c"))

    def test_app_order(self):
        _, body = one("app_order", V3, device="d", order=["Time", "Date"], disabled=["Battery"])
        self.assertEqual(
            body, [{"name": "Time", "show": True, "pos": 0}, {"name": "Date", "show": True, "pos": 1}, {"name": "Battery", "show": False}]
        )

    def test_ng_only_actions_rejected(self):
        for action in ("stop_sound", "reset_settings", "get_screen"):
            with self.assertRaises(messages.UnsupportedError):
                build(action, V3, device="d")
        with self.assertRaises(messages.UnsupportedError):
            build("play_sound", V3, device="d", mp3="beep")


class AwtrixNgTests(unittest.TestCase):
    def test_command_topics(self):
        self.assertEqual(one("dismiss", NG, device="d"), (f"{P}/cmd/notify/dismiss", ""))
        self.assertEqual(one("dismiss", NG, device="d", name="job"), (f"{P}/cmd/notify/dismiss/job", ""))
        self.assertEqual(one("next_app", NG, device="d"), (f"{P}/cmd/apps/next", ""))
        self.assertEqual(one("previous_app", NG, device="d"), (f"{P}/cmd/apps/previous", ""))
        self.assertEqual(one("reboot", NG, device="d"), (f"{P}/cmd/device/reboot", ""))
        self.assertEqual(one("reset_settings", NG, device="d"), (f"{P}/cmd/settings/reset", ""))
        self.assertEqual(one("get_screen", NG, device="d"), (f"{P}/cmd/screen/get", ""))
        self.assertEqual(one("power", NG, device="d", power=True), (f"{P}/cmd/display", {"power": True}))
        with self.assertRaises(messages.UnsupportedError):
            build("update_firmware", NG, device="d")

    def test_switch_app(self):
        self.assertEqual(
            one("switch_app", NG, device="d", name="Time", fast=True), (f"{P}/cmd/apps/switch", {"name": "Time", "fast": True})
        )
        self.assertEqual(one("switch_app", NG, device="d", name="Time"), (f"{P}/cmd/apps/switch", {"name": "Time"}))

    def test_deep_sleep_converts_to_ms(self):
        self.assertEqual(one("deep_sleep", NG, device="d", sleep=120), (f"{P}/cmd/device/sleep", {"durationMs": 120000}))

    def test_overlay(self):
        self.assertEqual(one("overlay", NG, device="d", overlay="Drizzle"), (f"{P}/cmd/display", {"overlay": "Drizzle"}))
        self.assertEqual(one("overlay", NG, device="d", overlay="clear"), (f"{P}/cmd/display", {"overlay": None}))

    def test_moodlight(self):
        self.assertEqual(
            one("moodlight", NG, device="d", color="#3366FF", brightness=120, kelvin=3000),
            (f"{P}/cmd/display/moodlight", {"color": "#3366FF", "brightness": 120}),
        )
        self.assertEqual(one("moodlight", NG, device="d", enabled=False), (f"{P}/cmd/display/moodlight", ""))

    def test_indicator(self):
        self.assertEqual(
            one("indicator", NG, device="d", indicator=1, color="#FF0000", blink=500, fade=200),
            (f"{P}/cmd/indicators/1", {"color": "#FF0000", "blinkMs": 500, "fadeMs": 200}),
        )
        self.assertEqual(one("indicator", NG, device="d", indicator=3, enabled=False), (f"{P}/cmd/indicators/3", ""))
        with self.assertRaises(ValueError):
            build("indicator", NG, device="d", indicator=4)

    def test_audio(self):
        self.assertEqual(one("play_sound", NG, device="d", mp3="beep"), (f"{P}/cmd/audio/play", {"mp3": "beep"}))
        self.assertEqual(one("play_sound", NG, device="d", track="12"), (f"{P}/cmd/audio/play", {"track": 12}))
        with self.assertRaises(ValueError):
            build("play_sound", NG, device="d", mp3="a", track=1)
        with self.assertRaises(ValueError):
            build("play_sound", NG, device="d")
        self.assertEqual(one("stop_sound", NG, device="d"), (f"{P}/cmd/audio/stop", ""))
        self.assertEqual(one("stop_sound", NG, device="d", scope="stream"), (f"{P}/cmd/audio/stop", {"scope": "stream"}))

    def test_app_order(self):
        self.assertEqual(one("app_order", NG, device="d", disabled=["Battery"]), (f"{P}/cmd/apps/order", {"disabled": ["Battery"]}))
        self.assertEqual(
            one("app_order", NG, device="d", order=["Time"], disabled=[]),
            (f"{P}/cmd/apps/order", {"disabled": [], "order": ["Time"]}),
        )

    def test_custom_app_translated(self):
        topic, body = one("custom_app", NG, device="d", app="weather", text="21", color="#FF0000", duration=5, icon="2422")
        self.assertEqual(topic, f"{P}/cmd/apps/pushed/weather")
        self.assertEqual(body, {"text": "21", "textColor": "#FF0000", "durationMs": 5000, "icon": "2422"})

    def test_custom_app_ng_native_keys_pass_through(self):
        _, body = one("custom_app", NG, device="d", app="x", text="hi", overlay="snow", effect="Plasma", effectSpeed=2, palette="Lava")
        self.assertEqual(body, {"text": "hi", "overlay": "snow", "effect": "Plasma", "effectSpeed": 2, "palette": "Lava"})

    def test_custom_app_validation(self):
        with self.assertRaises(ValueError):
            build("custom_app", NG, device="d", app="bad name!", text="x")
        with self.assertRaises(ValueError):
            build("custom_app", NG, device="d", app="x")
        with self.assertRaises(ValueError):
            build("delete_custom_app", NG, device="d", app="a/b")

    def test_notification_translated(self):
        topic, body = one("notification", NG, device="d", text="Door", color="#FF0000", duration=10, rtttl="a:d=4:c", hold=True)
        self.assertEqual(topic, f"{P}/cmd/notify")
        self.assertEqual(body, {"text": "Door", "textColor": "#FF0000", "durationMs": 10000, "soundRtttl": "a:d=4:c", "hold": True})

    def test_settings_translated_and_split(self):
        msgs = build("settings", NG, device="d", BRI=80, ATIME=5, MATP=False, OVERLAY="snow", brightness=10)
        by_topic = {m.topic: json.loads(m.payload) for m in msgs}
        self.assertEqual(by_topic[f"{P}/cmd/settings"], {"brightness": 10, "appDurationMs": 5000})
        self.assertEqual(by_topic[f"{P}/cmd/display"], {"power": False, "overlay": "snow"})

    def test_settings_only_display(self):
        (msg,) = build("settings", NG, device="d", OVERLAY="clear")
        self.assertEqual((msg.topic, json.loads(msg.payload)), (f"{P}/cmd/display", {"overlay": None}))


if __name__ == "__main__":
    unittest.main()
