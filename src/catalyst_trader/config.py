"""Env-first configuration. API keys never hardcoded — read from env / .env only."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    fmp_api_key: str | None = None  # env: FMP_API_KEY
    db_path: str = "catalyst.db"
    freshness_near_event_hours: int = 48
    freshness_default_days: int = 7
    ctgov_request_spacing_s: float = 1.5


settings = Settings()
