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

    # Operational defaults live only here; every field accepts an uppercase env override.
    cors_origins_csv: str = "http://localhost:5173,http://127.0.0.1:5173,https://a2r-vidora.vercel.app,https://vidoraa.com"
    chat_model: str = "openai/gpt-oss-20b"
    stt_model: str = "whisper-large-v3"
    answer_max_tokens: int = Field(1024, gt=0)
    answer_temperature: float = Field(0.2, ge=0, le=2)
    provider_timeout_seconds: float = Field(60, gt=0)
    summary_max_tokens: int = Field(400, gt=0)
    summary_max_input_chars: int = Field(20000, gt=0)
    submit_limit: int = Field(5, gt=0)
    submit_window_seconds: int = Field(600, gt=0)
    question_limit: int = Field(10, gt=0)
    question_window_seconds: int = Field(600, gt=0)
    rate_limit_max_buckets: int = Field(10000, gt=0)
    admission_timeout_seconds: float = Field(5, gt=0)
    recaptcha_verify_url: str = "https://www.google.com/recaptcha/api/siteverify"
    recaptcha_timeout_seconds: float = Field(5, gt=0)
    cookie_cache_ttl_seconds: int = Field(1800, gt=0)
    max_video_duration_seconds: int = Field(2100, gt=0)
    download_timeout_seconds: float = Field(20, gt=0)
    download_retries: int = Field(2, ge=0)
    audio_quality: str = "64"
    analysis_timeout_seconds: float = Field(270, gt=0)
    stale_processing_seconds: int = Field(600, gt=0)
    target_chunk_chars: int = Field(500, gt=0)
    max_chunk_chars: int = Field(800, gt=0)
    max_question_chars: int = Field(2000, gt=0)
    embedding_model: str = "all-MiniLM-L6-v2"
    embedding_batch_size: int = Field(32, gt=0)
    function_max_instances: int = Field(10, gt=0)
    function_memory_mb: int = Field(2048, gt=0)
    function_cpu: int = Field(1, gt=0)
    function_timeout_seconds: int = Field(300, gt=0)
    function_concurrency: int = Field(2, gt=0)
    task_max_attempts: int = Field(1, gt=0)
    task_max_concurrent_dispatches: int = Field(3, gt=0)
    video_processing_task: str = "processvideo"
    cleanup_schedule: str = "every 24 hours"
    qa_page_size: int = Field(20, gt=0)
    qa_max_page_size: int = Field(100, gt=0)
    retrieval_short_seconds: int = Field(600, gt=0)
    retrieval_medium_seconds: int = Field(1800, gt=0)
    retrieval_short_k: int = Field(5, gt=0)
    retrieval_medium_k: int = Field(8, gt=0)
    retrieval_long_k: int = Field(12, gt=0)
    retrieval_candidate_multiplier: int = Field(4, gt=0)
    retrieval_min_candidates: int = Field(20, gt=0)
    retrieval_rrf_k: int = Field(60, gt=0)

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
        if self.analysis_timeout_seconds >= self.function_timeout_seconds:
            raise ValueError("ANALYSIS_TIMEOUT_SECONDS must be below FUNCTION_TIMEOUT_SECONDS")
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
