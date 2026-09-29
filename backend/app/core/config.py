from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "postgresql+psycopg://sitescout:sitescout@localhost:5433/sitescout"

    jwt_secret: str = "dev-only-secret-change-me"
    jwt_expire_minutes: int = 720
    # Demo mode lets the persona switcher log in as a seeded user without a password.
    demo_mode: bool = True

    llm_base_url: str = "https://api.groq.com/openai/v1"
    llm_model: str = "openai/gpt-oss-120b"
    llm_api_key: str = ""
    llm_timeout_s: float = 30.0

    stores_api_url: str = (
        "https://internal-service.savomart.in/bridge/api/store/list?is_operational=True"
    )
    stores_api_token: str = ""

    nominatim_user_agent: str = "SavoSiteScout/0.1 (Savomart hackathon prototype; low-volume, cached)"

    cors_origins: str = "http://localhost:5173"
    media_dir: str = str(REPO_ROOT / "media")

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
