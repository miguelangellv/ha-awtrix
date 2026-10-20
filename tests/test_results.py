from __future__ import annotations

import unittest

from tests._load import results

P = "clock"


class ParseFailureTests(unittest.TestCase):
    def test_failure_with_field(self):
        payload = '{"ok":false,"error":{"code":"validationFailed","message":"out of range","field":"brightness"}}'
        out = results.parse_failure(P, f"{P}/cmd/settings/result", payload)
        self.assertEqual(out, {"command": "settings", "code": "validationFailed", "message": "out of range", "field": "brightness"})
        self.assertEqual(results.describe(out), "command 'settings' refused with validationFailed: out of range (field brightness)")

    def test_nested_command_name(self):
        payload = '{"ok":false,"error":{"code":"invalidName","message":"bad"}}'
        out = results.parse_failure(P, f"{P}/cmd/apps/pushed/x/result", payload)
        self.assertEqual(out["command"], "apps/pushed/x")
        self.assertIsNone(out["field"])

    def test_success_and_noise_are_ignored(self):
        self.assertIsNone(results.parse_failure(P, f"{P}/cmd/settings/result", '{"ok":true}'))
        self.assertIsNone(results.parse_failure(P, f"{P}/cmd/settings/result", "not json"))
        self.assertIsNone(results.parse_failure(P, f"{P}/cmd/settings/result", "[]"))
        self.assertIsNone(results.parse_failure(P, f"{P}/cmd/settings/result", '{"hello":1}'))
        self.assertIsNone(results.parse_failure(P, f"{P}/state/device", '{"ok":false}'))
        self.assertIsNone(results.parse_failure(P, "other/cmd/settings/result", '{"ok":false}'))

    def test_failure_without_error_body(self):
        out = results.parse_failure(P, f"{P}/cmd/display/result", '{"ok":false}')
        self.assertEqual(out["code"], "unknown")

    def test_dismissing_a_missing_notification_is_benign(self):
        gone = results.parse_failure(
            P, f"{P}/cmd/notify/dismiss/alert/result", '{"ok":false,"error":{"code":"notFound","message":"not found"}}'
        )
        self.assertTrue(results.is_benign(gone))
        other = results.parse_failure(P, f"{P}/cmd/apps/switch/result", '{"ok":false,"error":{"code":"notFound","message":"not found"}}')
        self.assertFalse(results.is_benign(other))

    def test_subscription_filters(self):
        self.assertEqual(results.result_topics(P), [f"{P}/cmd/+/result", f"{P}/cmd/+/+/result", f"{P}/cmd/+/+/+/result"])


if __name__ == "__main__":
    unittest.main()
