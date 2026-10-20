"""Read the ``<command topic>/result`` replies of AWTRIX NG.

Every command that matches a route is answered on ``<command topic>/result`` with ``{"ok": true}`` or
``{"ok": false, "error": {"code", "message", "field"?}}``. A command the firmware rejects therefore fails
silently unless somebody reads those replies. Pure Python, no Home Assistant imports.
"""

from __future__ import annotations

import json
from typing import Any

# Reply topics sit one to three levels below <prefix>/cmd/ (settings, display/moodlight, apps/pushed/<name>).
RESULT_FILTERS = ("cmd/+/result", "cmd/+/+/result", "cmd/+/+/+/result")

EVENT_COMMAND_FAILED = "awtrix_command_failed"


def result_topics(prefix: str) -> list[str]:
    """MQTT subscription filters that cover every reply of one device."""
    return [f"{prefix}/{f}" for f in RESULT_FILTERS]


def parse_failure(prefix: str, topic: str, payload: str | bytes) -> dict[str, Any] | None:
    """Return the failure carried by a reply, or ``None`` for a success or anything that is not a reply."""
    start, end = f"{prefix}/cmd/", "/result"
    if not (topic.startswith(start) and topic.endswith(end)):
        return None
    try:
        data = json.loads(payload)
    except (TypeError, ValueError):
        return None
    if not isinstance(data, dict) or data.get("ok") is not False:
        return None

    error = data.get("error") if isinstance(data.get("error"), dict) else {}
    return {
        "command": topic[len(start) : -len(end)],
        "code": error.get("code", "unknown"),
        "message": error.get("message", ""),
        "field": error.get("field"),
    }


def is_benign(failure: dict[str, Any]) -> bool:
    """Refusals that carry no news: dismissing a notification that is not (or no longer) there."""
    return failure.get("code") == "notFound" and str(failure.get("command", "")).startswith("notify/dismiss")


def describe(failure: dict[str, Any]) -> str:
    """One human line for a log entry."""
    field = f" (field {failure['field']})" if failure.get("field") else ""
    message = f": {failure['message']}" if failure.get("message") else ""
    return f"command '{failure['command']}' refused with {failure['code']}{message}{field}"
