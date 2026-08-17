"""Env-first configuration. API keys never hardcoded — read from env / .env only."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    fmp_api_key: str | None = None  # env: FMP_API_KEY
    sec_user_agent: str | None = None  # env: SEC_USER_AGENT — SEC requires a declared UA with contact email
    alpha_vantage_api_key: str | None = None  # env: ALPHA_VANTAGE_API_KEY — GREEN weekly source when set
    tiingo_api_key: str | None = None  # env: TIINGO_API_KEY — GREEN EOD source when set
    fred_api_key: str | None = None  # env: FRED_API_KEY — GREEN macro/rates/VIX source when set
    rh_mcp_url: str | None = None  # env: RH_MCP_URL — RH Agentic MCP endpoint; presence signals the MCP is configured.
    # The actual read callable is RUNTIME-BOUND by the Claude Agent SDK at desk startup as
    # settings.rh_mcp_call (RH-DATA-03 live-binding). registry gates the RH slots on
    # getattr(settings, "rh_mcp_call", None) — None until the SDK binds it (mirrors the FRED-key gate).
    db_path: str = "catalyst.db"
    raw_snapshot_dir: str = "data/raw"  # env: RAW_SNAPSHOT_DIR — raw-response lake ($0 local disk)
    raw_cache_ttl_s: int = 0  # env: RAW_CACHE_TTL_S — >0 enables the persistent read-through over the
    # raw lake: an archived response for the exact request within this many seconds is reused instead
    # of re-fetched (frugality: never re-call data we already have). 0 = off (default; hermetic tests).
    freshness_near_event_hours: int = 48
    freshness_default_days: int = 7
    ctgov_request_spacing_s: float = 1.5


settings = Settings()
