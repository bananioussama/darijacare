"""JSON logs (one object per line). Messages never contain customer texts.

The access log records method, path, status, duration and a request id; request
bodies (customer messages, passwords) are never logged.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

EXTRA_FIELDS = (
    "request_id",
    "method",
    "path",
    "status",
    "duration_ms",
    "client",
    "action",
    "rule",
    "intent",
    "escalation",
)


class JsonFormatter(logging.Formatter):
    """Format records as JSON with a UTC timestamp and the known extra fields."""

    def format(self, record: logging.LogRecord) -> str:
        data: dict[str, object] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for name in EXTRA_FIELDS:
            if hasattr(record, name):
                data[name] = getattr(record, name)
        if record.exc_info:
            data["exc"] = self.formatException(record.exc_info)
        return json.dumps(data, ensure_ascii=False, default=str)


def configure_json_logging(level: int = logging.INFO) -> None:
    """Send every log record to stderr as JSON (replaces existing handlers)."""
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
