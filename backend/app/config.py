"""Application configuration.

Everything is driven by environment variables with safe defaults so the app
runs with zero setup in DEMO_MODE. Real data sources only kick in when the
relevant keys are present.
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- Runtime -----------------------------------------------------------
    # When True, every endpoint serves deterministic fixture data and no
    # outbound network / paid API call is ever made. This is the default so a
    # fresh clone (or a Docker image with no secrets) just works.
    demo_mode: bool = True

    # --- SEC EDGAR ---------------------------------------------------------
    # EDGAR is free and needs no key, but it REQUIRES a descriptive User-Agent
    # naming you + an email, or it returns 403 and can block your IP ~10 min.
    sec_user_agent: str = "StockTrends-AI dev (set SEC_USER_AGENT to a real email)"

    # --- Market data / news (Finnhub free tier: 60 req/min) ----------------
    finnhub_api_key: str = ""

    # --- AI (Anthropic) ----------------------------------------------------
    anthropic_api_key: str = ""
    # Cheap model handles the first extraction pass; the router escalates to the
    # stronger model only on low-confidence fields.
    extract_model_cheap: str = "claude-haiku-4-5-20251001"
    extract_model_strong: str = "claude-sonnet-5"

    # --- CORS --------------------------------------------------------------
    # Comma-separated origins allowed to call the API from a browser.
    cors_origins: str = "*"

    @property
    def has_anthropic(self) -> bool:
        return bool(self.anthropic_api_key)

    @property
    def has_finnhub(self) -> bool:
        return bool(self.finnhub_api_key)

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
