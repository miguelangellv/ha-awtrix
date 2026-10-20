from __future__ import annotations

import unittest

from tests._load import translate as t


class AppPayloadTests(unittest.TestCase):
    def test_renames_and_units(self):
        out = t.translate_app_payload(
            {"color": "#FFF", "background": "#000", "lifetime": 60, "lifetimeMode": 1, "pushIcon": 2, "blinkText": 500}
        )
        self.assertEqual(
            out,
            {
                "textColor": "#FFF",
                "backgroundColor": "#000",
                "lifetimeMs": 60000,
                "lifetimeExpiry": "mark",
                "iconMode": "push",
                "textBlinkMs": 500,
            },
        )

    def test_scroll_options_merge(self):
        out = t.translate_app_payload({"noScroll": True, "scrollSpeed": 50})
        self.assertEqual(out, {"scroll": {"mode": "static", "speed": 50}})
        self.assertEqual(t.translate_app_payload({"noScroll": False}), {})

    def test_fragments(self):
        out = t.translate_app_payload({"text": [{"t": "A", "c": "#F00"}, {"t": "B"}]})
        self.assertEqual(out["text"], [{"text": "A", "color": "#F00"}, {"text": "B"}])

    def test_draw_commands(self):
        out = t.translate_app_payload(
            {"draw": [{"dp": [1, 2, "#F00"]}, {"df": [0, 0, 4, 4, "#0F0"]}, {"dt": [0, 0, "Hi", "#00F"]}, {"dfc": [5, 5, 2, "#FFF"]}]}
        )
        self.assertEqual(
            out["draw"],
            [["pixel", 1, 2, "#F00"], ["rectFill", 0, 0, 4, 4, "#0F0"], ["text", 0, 0, "Hi", "#00F"], ["circleFill", 5, 5, 2, "#FFF"]],
        )

    def test_native_draw_kept(self):
        self.assertEqual(t.translate_app_payload({"draw": [["pixel", 1, 1, "#F00"]]})["draw"], [["pixel", 1, 1, "#F00"]])

    def test_rainbow_and_gradient_use_palette(self):
        self.assertEqual(t.translate_app_payload({"rainbow": True}), {"textColor": "palette", "palette": "Rainbow"})
        out = t.translate_app_payload({"gradient": ["#F00", "#00F"]})
        self.assertEqual(out, {"textColor": "palette", "palette": ["#F00", "#00F"]})

    def test_effect_settings(self):
        out = t.translate_app_payload({"effect": "Plasma", "effectSettings": {"speed": 50, "palette": "Lava", "blend": False}})
        self.assertEqual(out, {"effect": "Plasma", "effectSpeed": 10.0, "palette": "Lava", "paletteBlend": False})

    def test_overlay_clear_dropped(self):
        self.assertEqual(t.translate_app_payload({"overlay": "clear"}), {})
        self.assertEqual(t.translate_app_payload({"overlay": "rain"}), {"overlay": "rain"})

    def test_v3_only_keys_dropped(self):
        self.assertEqual(t.translate_app_payload({"save": True, "pos": 2, "topText": True, "text": "x"}), {"text": "x"})


class SettingsTests(unittest.TestCase):
    def test_transition_index(self):
        self.assertEqual(t.translate_settings({"TEFF": "1"})[0], {"transitionEffect": "Slide"})
        self.assertEqual(t.translate_settings({"TEFF": 99})[2], ["TEFF"])

    def test_nested_weekday_bar_and_scroll(self):
        s, _, _ = t.translate_settings({"WD": True, "WDCA": "#FFF", "SOM": False, "SSPEED": 80})
        self.assertEqual(s, {"weekdayBar": {"show": True, "activeColor": "#FFF", "startOnMonday": False}, "scroll": {"speed": 80}})

    def test_time_format(self):
        s, _, _ = t.translate_settings({"TFORMAT": "hh:mm:ss"})
        self.assertEqual(s, {"time24h": False, "timeShowSeconds": True})
        s, _, _ = t.translate_settings({"TFORMAT": "HH:mm"})
        self.assertEqual(s, {"time24h": True, "timeShowSeconds": False})

    def test_volume_scaled(self):
        s, _, _ = t.translate_settings({"VOL": 15})
        self.assertEqual(s, {"buzzerVolume": 50, "dfplayerVolume": 50})

    def test_unsupported_reported(self):
        _, _, unsupported = t.translate_settings({"TMODE": 1, "TIM": True, "BRI": 3})
        self.assertEqual(sorted(unsupported), ["TIM", "TMODE"])

    def test_overlay_and_power_go_to_display(self):
        s, d, _ = t.translate_settings({"OVERLAY": "clear", "MATP": True})
        self.assertEqual((s, d), ({}, {"overlay": None, "power": True}))


if __name__ == "__main__":
    unittest.main()
