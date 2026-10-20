"""Discovery documents: structure, and that every Jinja template renders what the firmware expects."""

from __future__ import annotations

import json
import unittest

from jinja2 import Environment

from tests._load import discovery

UID = "aabbccddeeff"
P = "clock"
ENV = Environment()


def render(template: str, **variables) -> str:
    return ENV.from_string(template).render(**variables).strip()


class StructureTests(unittest.TestCase):
    def setUp(self):
        self.entities = discovery.build_entities(P, UID)
        self.by_key = {topic.split("/")[-2][4:]: (topic, cfg) for topic, cfg in self.entities}

    def test_topics_and_unique_ids_are_unique_and_well_formed(self):
        topics = [t for t, _ in self.entities]
        ids = [c["unique_id"] for _, c in self.entities]
        self.assertEqual(len(topics), len(set(topics)))
        self.assertEqual(len(ids), len(set(ids)))
        for topic, cfg in self.entities:
            component = topic.split("/")[1]
            self.assertTrue(topic.startswith(f"homeassistant/{component}/{UID}/ext_"))
            self.assertTrue(topic.endswith("/config"))
            self.assertEqual(cfg["device"], {"identifiers": [UID]})
            self.assertEqual(cfg["availability_topic"], f"{P}/availability")
            self.assertTrue(cfg["unique_id"].startswith(f"{UID}_ext_"))
            json.loads(discovery.encode(cfg))

    def test_device_name_is_included_when_known(self):
        named = discovery.build_entities(P, UID, device_name="Clock")
        self.assertTrue(all(c["device"] == {"identifiers": [UID], "name": "Clock"} for _, c in named))
        self.assertTrue(all("name" not in c["device"] for _, c in self.entities))

    def test_discovery_prefix_is_configurable(self):
        topic, _ = discovery.build_entities(P, UID, discovery_prefix="ha")[0]
        self.assertTrue(topic.startswith("ha/"))

    def test_commands_go_to_the_cmd_topics_and_state_comes_from_retained_topics(self):
        for topic, cfg in self.entities:
            if "command_topic" in cfg:
                self.assertTrue(cfg["command_topic"].startswith(f"{P}/cmd/"), topic)
            if "state_topic" in cfg:
                self.assertIn(cfg["state_topic"], (f"{P}/state/settings", f"{P}/state/device"), topic)

    def test_hardware_dependent_and_noisy_entities_start_disabled(self):
        for key in ("buzzerVolume", "dfplayerVolume", "mp3Volume", "fps", "messageCount", "psramFree"):
            self.assertIs(self.by_key[key][1]["enabled_by_default"], False, key)

    def test_overlay_options_come_from_capabilities(self):
        default = dict(self.by_key["overlay"][1])["options"]
        self.assertEqual(default[0], "none")
        custom = discovery.build_entities(P, UID, overlays=["rain", "hail"])
        options = next(c for t, c in custom if t.endswith("ext_overlay/config"))["options"]
        self.assertEqual(options, ["none", "rain", "hail"])


class TemplateTests(unittest.TestCase):
    def setUp(self):
        self.by_key = {t.split("/")[-2][4:]: c for t, c in discovery.build_entities(P, UID)}

    def test_overlay_command(self):
        tpl = self.by_key["overlay"]["command_template"]
        self.assertEqual(json.loads(render(tpl, value="rain")), {"overlay": "rain"})
        self.assertEqual(json.loads(render(tpl, value="none")), {"overlay": None})

    def test_moodlight_command(self):
        cfg = self.by_key["moodlight"]
        body = json.loads(render(cfg["command_on_template"], red=51, green=102, blue=255, brightness=120))
        self.assertEqual(body, {"color": "#3366ff", "brightness": 120})
        defaults = json.loads(render(cfg["command_on_template"]))
        self.assertEqual(defaults, {"color": "#ffffff", "brightness": 120})
        self.assertEqual(render(cfg["command_off_template"]), "")

    def test_numbers(self):
        settings = {"buzzerVolume": 70, "dfplayerVolume": 5, "mp3Volume": 10, "saturation": 90, "appDurationMs": 7000}
        for key, value in settings.items():
            cfg = self.by_key[key]
            self.assertEqual(json.loads(render(cfg["command_template"], value=float(value))), {key: value})
            self.assertEqual(render(cfg["value_template"], value_json=settings), str(value))

    def test_switches(self):
        for key in ("time24h", "timeShowSeconds", "useCelsius", "uppercase", "blockNavigation"):
            cfg = self.by_key[key]
            self.assertEqual(json.loads(render(cfg["command_template"], value="ON")), {key: True})
            self.assertEqual(json.loads(render(cfg["command_template"], value="OFF")), {key: False})
            self.assertEqual(render(cfg["value_template"], value_json={key: True}), "ON")
            self.assertEqual(render(cfg["value_template"], value_json={key: False}), "OFF")

    def test_selects_on_settings(self):
        for key, value in (("timeSeparatorMode", "pulse"), ("transitionDirection", "reverse")):
            cfg = self.by_key[key]
            self.assertIn(value, cfg["options"])
            self.assertEqual(json.loads(render(cfg["command_template"], value=value)), {key: value})
            self.assertEqual(render(cfg["value_template"], value_json={key: value}), value)

    def test_diagnostic_sensors(self):
        device = {
            "minFreeHeapBytes": 91560,
            "largestFreeBlockBytes": 65536,
            "resetReason": "software",
            "fps": 38,
            "messageCount": 12,
            "mqtt": {"connects": 3, "lastError": None},
        }
        expected = {
            "minFreeHeap": "91560",
            "largestFreeBlock": "65536",
            "resetReason": "software",
            "mqttConnects": "3",
            "mqttLastError": "none",
            "fps": "38",
            "messageCount": "12",
        }
        for key, want in expected.items():
            self.assertEqual(render(self.by_key[key]["value_template"], value_json=device), want, key)
        # Boards without PSRAM omit the field; it must not break the template.
        self.assertEqual(render(self.by_key["psramFree"]["value_template"], value_json=device), "None")


class CapabilitiesTests(unittest.TestCase):
    def test_overlays_extracted(self):
        self.assertEqual(discovery.overlays_from_capabilities('{"overlays":["rain","snow"],"effects":[]}'), ["rain", "snow"])

    def test_bad_input_is_ignored(self):
        for payload in (None, "", "not json", "[]", '{"overlays":[]}', '{"overlays":[1]}', '{"effects":[]}'):
            self.assertIsNone(discovery.overlays_from_capabilities(payload), payload)


if __name__ == "__main__":
    unittest.main()
