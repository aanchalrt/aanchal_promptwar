"""
Application configuration loaded from environment variables.

Secrets are loaded from Google Secret Manager when GCP_PROJECT and
SECRET_NAME environment variables are set; otherwise falls back to the
GEMINI_API_KEY environment variable.
"""

from __future__ import annotations

import os
from functools import lru_cache


def _load_secret_from_gcp(project: str, secret_name: str) -> str | None:
    """
    Retrieve a secret value from Google Secret Manager.

    Args:
        project: The GCP project ID.
        secret_name: The secret resource name (without version).

    Returns:
        The secret string value, or None if unavailable.
    """
    try:
        from google.cloud import secretmanager  # type: ignore[import]

        client = secretmanager.SecretManagerServiceClient()
        name = f"projects/{project}/secrets/{secret_name}/versions/latest"
        response = client.access_secret_version(request={"name": name})
        return response.payload.data.decode("utf-8").strip()
    except Exception:
        return None


class Settings:
    """
    Central application settings.

    Attributes:
        gemini_api_key: API key for the Gemini service.
        gemini_model: Model identifier used for all Gemini calls.
        mock_mode: When True, no real Gemini calls are made.
        rate_limit_rpm: Max requests per minute per IP on /api/analyze.
        log_level: Python logging level string.
    """

    def __init__(self) -> None:
        # --- GCP / Secret Manager ---
        gcp_project = os.getenv("GCP_PROJECT", "")
        secret_name = os.getenv("SECRET_NAME", "")

        if gcp_project and secret_name:
            self.gemini_api_key: str = _load_secret_from_gcp(gcp_project, secret_name) or os.getenv(
                "GEMINI_API_KEY", ""
            )
        else:
            self.gemini_api_key = os.getenv("GEMINI_API_KEY", "")

        # --- Model ---
        self.gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")

        # --- Modes ---
        self.mock_mode: bool = os.getenv("MOCK_MODE", "false").lower() in ("1", "true", "yes")

        # --- Rate limiting ---
        self.rate_limit_rpm: int = int(os.getenv("RATE_LIMIT_RPM", "20"))

        # --- Logging ---
        self.log_level: str = os.getenv("LOG_LEVEL", "INFO")

        # --- Cache ---
        self.cache_max_size: int = int(os.getenv("CACHE_MAX_SIZE", "128"))


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the singleton Settings instance (cached after first call)."""
    return Settings()
