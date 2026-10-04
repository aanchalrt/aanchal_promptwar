"""
Structured logging setup for BlindSpot AI.

Uses google-cloud-logging when running on GCP (GCP_PROJECT is set),
otherwise falls back to plain structured JSON logging to stdout.
Sensitive data (decision text, user input) is NEVER logged.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import uuid
from typing import Any


class _JSONFormatter(logging.Formatter):
    """Format log records as single-line JSON for Cloud Logging ingestion."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict[str, Any] = {
            "severity": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
            "timestamp": self.formatTime(record),
        }
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry)


def setup_logging(level: str = "INFO") -> None:
    """
    Configure application-wide logging.

    When GCP_PROJECT is set, attempts to initialise google-cloud-logging
    for structured log ingestion. Falls back to JSON stdout logging.

    Args:
        level: Python logging level string, e.g. "INFO" or "DEBUG".
    """
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    gcp_project = os.getenv("GCP_PROJECT", "")
    if gcp_project:
        try:
            import google.cloud.logging  # type: ignore[import]

            cloud_client = google.cloud.logging.Client()
            cloud_client.setup_logging(log_level=numeric_level)
            logging.getLogger("blindspot_ai").info(
                "cloud_logging=enabled project=%s", gcp_project
            )
            return
        except ImportError:
            pass  # Fall through to JSON logging

    # Local / fallback: JSON to stdout
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_JSONFormatter())
    logging.basicConfig(level=numeric_level, handlers=[handler])


def get_request_id() -> str:
    """Generate a unique request ID for log correlation."""
    return str(uuid.uuid4())[:8]
