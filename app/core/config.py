import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def _strategos_env_files() -> tuple[str, ...]:
    """
    Load env in order; later files override earlier (local .env wins over shared credentials).

    Shared file (gitignored): <parent-of-strategos-api>/credentials/strategos-api.env
    e.g. intelligence/credentials/strategos-api.env when API is at intelligence/strategos-api/

    Optional: STRATEGOS_EXTRA_ENV_FILE=/absolute/path.env (highest priority).
    """
    api_root = Path(__file__).resolve().parents[2]
    paths: list[str] = []
    shared = api_root.parent / "credentials" / "strategos-api.env"
    if shared.is_file():
        paths.append(str(shared))
    local = api_root / ".env"
    if local.is_file():
        paths.append(str(local))
    extra = (os.environ.get("STRATEGOS_EXTRA_ENV_FILE") or "").strip()
    if extra and Path(extra).is_file():
        paths.append(extra)
    if not paths:
        paths.append(str(local))
    return tuple(paths)


class Settings(BaseSettings):
    PROJECT_NAME: str = "STRATEGOS API"
    API_V1_PREFIX: str = "/api/v1"
    DEBUG: bool = False

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://strategos:strategos@localhost:5432/strategos"
    DATABASE_URL_SYNC: str = "postgresql://strategos:strategos@localhost:5432/strategos"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # LLM — NEVER hardcode model strings
    LLM_PRIMARY_MODEL: str = "claude-sonnet-4-6"
    LLM_FALLBACK_MODEL: str = "gpt-4o"
    LLM_MAX_TOKENS_PER_CALL: int = 1000
    LLM_CONTEXT_TOKEN_BUDGET: int = 8000

    # API Keys (from environment / secrets manager)
    ANTHROPIC_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    NEWSAPI_KEY: str = ""
    POLYGON_API_KEY: str = ""
    ALPHA_VANTAGE_KEY: str = ""
    METALS_API_KEY: str = ""
    OPEN_EXCHANGE_RATES_KEY: str = ""
    CLOUDFLARE_RADAR_TOKEN: str = ""
    FRED_API_KEY: str = ""
    GDELT_API_URL: str = "https://api.gdeltproject.org/api/v2"
    X_BEARER_TOKEN: str = ""
    REDDIT_CLIENT_ID: str = ""
    REDDIT_CLIENT_SECRET: str = ""
    TELEGRAM_API_ID: str = ""
    TELEGRAM_API_HASH: str = ""
    # Comma-separated @usernames or numeric channel IDs (primary L2 — conflict monitoring)
    TELEGRAM_CHANNELS: str = ""
    # From Telethon StringSession — generate once via scripts/telegram_session_setup.py
    TELEGRAM_SESSION_STRING: str = ""
    # NASA FIRMS area API — free registration: https://firms.modaps.eosdis.nasa.gov/api/map_key/
    NASA_FIRMS_MAP_KEY: str = ""
    MAPBOX_TOKEN: str = ""
    PINECONE_API_KEY: str = ""
    PINECONE_ENVIRONMENT: str = "us-east-1"
    PINECONE_INDEX_NAME: str = "strategos-signals"
    SENTRY_DSN: str = ""

    # Auth0
    AUTH0_DOMAIN: str = ""
    AUTH0_API_AUDIENCE: str = ""
    AUTH0_ALGORITHMS: list[str] = ["RS256"]

    # CORS
    CORS_ORIGINS: list[str] = [
        "http://localhost:3000",
        "http://localhost:3001",
    ]

    # Convergence weights
    LAYER_WEIGHTS: dict[str, float] = {
        "L1": 0.6,   # Editorial — high bias risk
        "L2": 0.6,   # Social — high noise
        "L3": 1.2,   # Shipping — ground truth
        "L4": 1.2,   # Aviation — ground truth
        "L5": 0.9,   # Commodities — partially manipulable
        "L6": 0.9,   # Currency — partially manipulable
        "L7": 0.9,   # Equity — partially manipulable
        "L8": 1.2,   # Satellite — ground truth
        "L9": 0.9,   # Economic — gov reporting bias
        "L10": 1.2,  # Connectivity — network reality
    }

    model_config = SettingsConfigDict(
        env_file=_strategos_env_files(),
        env_file_encoding="utf-8",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
