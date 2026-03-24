from pydantic_settings import BaseSettings
from functools import lru_cache


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
    ALPHA_VANTAGE_KEY: str = ""
    METALS_API_KEY: str = ""
    OPEN_EXCHANGE_RATES_KEY: str = ""
    MAPBOX_TOKEN: str = ""
    PINECONE_API_KEY: str = ""

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

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
