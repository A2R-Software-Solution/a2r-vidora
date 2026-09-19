"""Environment settings: definitions and validation; values come from .env."""
from functools import lru_cache
from pathlib import Path
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[2] / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    environment: str
    ai_enabled: bool
    app_name: str
    video_retention_hours: int = Field(gt=0)
    pool_pre_ping: bool
    pool_size: int
    max_overflow: int
    pool_recycle: int

    database_url: str | None = None
    groq_api_key: str | None = None
    groq_api_key_fallback: str | None = None
    recaptcha_secret_key: str | None = None
    recaptcha_min_score: float
    recaptcha_allowed_hostnames_csv: str
    google_credentials_path: str | None = None
    
    gcp_project_id: str | None = None
    youtube_cookie_secret_ids: list[str]

    # Required operational settings: values are supplied by environment files.
    cors_origins_csv: str
    chat_model: str
    stt_model: str
    answer_max_tokens: int = Field(gt=0)
    answer_temperature: float
    provider_timeout_seconds: float
    summary_max_tokens: int = Field(gt=0)
    summary_max_input_chars: int = Field(gt=0)
    submit_limit: int = Field(gt=0)
    submit_window_seconds: int = Field(gt=0)
    question_limit: int = Field(gt=0)
    question_window_seconds: int = Field(gt=0)
    # Enable only behind a trusted proxy; count forwarded entries from the right.
    rate_limit_trusted_proxy_hops: int = Field(default=0, ge=0)
    recaptcha_verify_url: str
    recaptcha_timeout_seconds: float
    cookie_cache_ttl_seconds: int = Field(gt=0)
    max_video_duration_seconds: int = Field(gt=0)
    download_timeout_seconds: float
    download_retries: int = Field(ge=0)
    audio_quality: str
    analysis_timeout_seconds: float
    stale_processing_seconds: int = Field(gt=0)
    target_chunk_chars: int = Field(gt=0)
    max_chunk_chars: int = Field(gt=0)
    max_question_chars: int = Field(gt=0)
    embedding_model: str
    embedding_batch_size: int = Field(gt=0)
    vidora_function_max_instances: int = Field(gt=0)
    vidora_function_memory_mb: int = Field(gt=0)
    vidora_function_cpu: int = Field(gt=0)
    vidora_function_timeout_seconds: int = Field(gt=0)
    vidora_function_concurrency: int = Field(gt=0)
    task_max_attempts: int = Field(gt=0)
    task_max_concurrent_dispatches: int = Field(gt=0)
    video_processing_task: str
    cleanup_schedule: str
    qa_page_size: int = Field(gt=0)
    qa_max_page_size: int = Field(gt=0)
    retrieval_short_seconds: int = Field(gt=0)
    retrieval_medium_seconds: int = Field(gt=0)
    retrieval_short_k: int = Field(gt=0)
    retrieval_medium_k: int = Field(gt=0)
    retrieval_long_k: int = Field(gt=0)
    retrieval_candidate_multiplier: int = Field(gt=0)
    retrieval_min_candidates: int = Field(gt=0)
    retrieval_rrf_k: int = Field(gt=0)

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins_csv.split(",") if origin.strip()]

    @model_validator(mode="after")
    def validate_budgets(self):
        if self.qa_page_size > self.qa_max_page_size:
            raise ValueError("QA_PAGE_SIZE must not exceed QA_MAX_PAGE_SIZE")
        if self.retrieval_short_seconds > self.retrieval_medium_seconds:
            raise ValueError("Retrieval duration thresholds must be ordered")
        if self.target_chunk_chars > self.max_chunk_chars:
            raise ValueError("TARGET_CHUNK_CHARS must not exceed MAX_CHUNK_CHARS")
        if self.analysis_timeout_seconds >= self.vidora_function_timeout_seconds:
            raise ValueError("ANALYSIS_TIMEOUT_SECONDS must be below VIDORA_FUNCTION_TIMEOUT_SECONDS")
        return self

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
