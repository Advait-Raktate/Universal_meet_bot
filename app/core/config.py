
"""
app/core/config.py
------------------
Single source of truth for all configuration & environment variables.
Uses Pydantic BaseSettings — reads from .env automatically.
Every router / service imports from here; never call os.getenv() elsewhere.
"""

import os
from typing import Optional
from pydantic import Field, computed_field
from pydantic_settings import BaseSettings
from pydantic import ConfigDict


class Settings(BaseSettings):

    # ── Recall.ai ─────────────────────────────────────────────────────────────
    recall_api_key: str  = Field(..., env="RECALL_API_KEY")
    recall_region:  str  = Field("us-west-2", env="RECALL_REGION")

    # ── App / Tunnel ──────────────────────────────────────────────────────────
    public_url:     str  = Field(..., env="PUBLIC_URL")
    downstream_api: str  = Field(..., env="DOWNSTREAM_API")

    # ── Google OAuth ──────────────────────────────────────────────────────────
    google_client_id:     str = Field(..., env="GOOGLE_CLIENT_ID")
    google_client_secret: str = Field(..., env="GOOGLE_CLIENT_SECRET")

    # ── App meta ──────────────────────────────────────────────────────────────
    environment: str = Field("development", env="ENVIRONMENT")
    debug:       bool = Field(False,        env="DEBUG")
    log_level:   str = Field("INFO",        env="LOG_LEVEL")

    # ── Derived / computed fields ─────────────────────────────────────────────
    @computed_field
    @property
    def recall_base_v1(self) -> str:
        return f"https://{self.recall_region}.recall.ai/api/v1"

    @computed_field
    @property
    def recall_base_v2(self) -> str:
        return f"https://{self.recall_region}.recall.ai/api/v2"

    @computed_field
    @property
    def recall_headers(self) -> dict:
        """Use for POST / PATCH — includes Content-Type."""
        return {
            "Authorization": f"Token {self.recall_api_key}",
            "Content-Type":  "application/json",
        }

    @computed_field
    @property
    def recall_headers_accept(self) -> dict:
        """Use for GET requests."""
        return {
            "Authorization": f"Token {self.recall_api_key}",
            "Accept":        "application/json",
        }

    @computed_field
    @property
    def webhook_recall_url(self) -> str:
        return f"{self.public_url}/webhook/recall"

    @computed_field
    @property
    def redirect_uri(self) -> str:
        return f"{self.public_url}/calendar/google_callback"

    @computed_field
    @property
    def google_scopes(self) -> str:
        return " ".join([
            "https://www.googleapis.com/auth/calendar.events.readonly",
            "https://www.googleapis.com/auth/userinfo.email",
        ])

    model_config = ConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


# ── Global instance ───────────────────────────────────────────────────────────
settings = Settings()

# ── Environment-specific overrides ────────────────────────────────────────────
if os.getenv("ENVIRONMENT") == "development":
    settings.debug     = True
    settings.log_level = "DEBUG"
elif os.getenv("ENVIRONMENT") == "production":
    settings.debug     = False
    settings.log_level = "WARNING"
