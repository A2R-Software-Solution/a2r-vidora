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
    app_name: str
    video_retention_hours: int
    pool_pre_ping: bool
    pool_size: int
    max_overflow: int
    pool_recycle: int

    database_url: str | None = None
    groq_api_key: str | None = None
    google_credentials_path: str | None = None
    
    gcp_project_id: str | None = None
    youtube_cookie_secret_ids: list[str] = []

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()