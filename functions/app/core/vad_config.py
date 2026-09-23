"""Shared VAD settings for application ingestion and the local listening preview."""
from pathlib import Path
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class VadSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[2] / ".env",
        extra="ignore", env_prefix="VAD_",
    )
    threshold: float = Field(default=0.5, gt=0, lt=1)
    # Keep the detector in speech state between these two thresholds.  This
    # avoids rapidly opening/closing a region when confidence hovers near the
    # speech threshold on noisy recordings.
    neg_threshold: float = Field(default=0.35, gt=0, lt=1)
    min_speech_ms: int = Field(default=250, gt=0)
    min_silence_ms: int = Field(default=100, gt=0)
    merge_pause_ms: int = Field(default=600, ge=0)
    speech_pad_ms: int = Field(default=150, ge=0)
    max_chunk_seconds: float = Field(default=30, gt=0, le=300)
    # A soft target prevents a chain of short utterances from always becoming
    # a near-maximum STT request; max_chunk_seconds remains the hard limit.
    group_target_seconds: float = Field(default=20, gt=0, le=300)
    split_overlap_ms: int = Field(default=250, ge=0)
    max_audio_seconds: int = Field(default=10805, gt=0)
    # A second packing stage combines these pause-based chunks for STT.
    stt_request_seconds: float = Field(default=240, gt=0, le=300)
    stt_request_bytes: int = Field(default=20_000_000, gt=44, le=24_000_000)

    @model_validator(mode="after")
    def validate_window(self):
        if self.neg_threshold >= self.threshold:
            raise ValueError("VAD_NEG_THRESHOLD must be below VAD_THRESHOLD")
        if self.group_target_seconds > self.max_chunk_seconds:
            raise ValueError("VAD_GROUP_TARGET_SECONDS must not exceed VAD_MAX_CHUNK_SECONDS")
        if self.stt_request_seconds < self.max_chunk_seconds:
            raise ValueError("VAD_STT_REQUEST_SECONDS must cover one VAD chunk")
        if self.stt_request_bytes < 44 + int(self.max_chunk_seconds * 16000) * 2:
            raise ValueError("VAD_STT_REQUEST_BYTES must cover one VAD WAV chunk")
        usable_ms = self.max_chunk_seconds * 1000 - 2 * self.speech_pad_ms
        if usable_ms < 1000 or self.split_overlap_ms >= usable_ms / 2:
            raise ValueError("Chunk must allow >=1 second of speech after padding, with overlap below half that duration")
        if self.merge_pause_ms and self.merge_pause_ms < self.min_silence_ms:
            raise ValueError("VAD_MERGE_PAUSE_MS must be zero or >= VAD_MIN_SILENCE_MS")
        return self
