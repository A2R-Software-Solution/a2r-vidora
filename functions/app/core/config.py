from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    environment: str
    ai_enabled: bool = True
    app_name: str
    video_retention_hours: int
    pool_pre_ping: bool
    pool_size: int
    max_overflow: int
    pool_recycle: int

    database_url: str | None = None
    groq_api_key: str | None = None
    groq_api_key_fallback: str | None = None
    recaptcha_secret_key: str | None = None
    recaptcha_min_score: float = 0.5
    recaptcha_allowed_hostnames_csv: str = ""
    google_credentials_path: str | None = None
    
    gcp_project_id: str | None = None
    youtube_cookie_secret_ids: list[str] = []

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"

    @property
    def recaptcha_allowed_hostnames(self) -> set[str]:
        return {
            hostname.strip().lower()
            for hostname in self.recaptcha_allowed_hostnames_csv.split(",")
            if hostname.strip()
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
