import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, String, Integer, Text, DateTime, Enum, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base


class VideoStatus(str, enum.Enum):
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class Video(Base):
    __tablename__ = "videos"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    # Credit wallet of a guest submitter, so the worker knows whom to charge.
    guest_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    guest_cap_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Submitted by an account holding purchased credits: priority lane and
    # paid retention for the video and its Shorts.
    priority: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    youtube_id: Mapped[str] = mapped_column(String(250), nullable=False)
    youtube_url: Mapped[str] = mapped_column(String(500), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=True)
    duration: Mapped[int] = mapped_column(Integer, nullable=True)
    status: Mapped[VideoStatus] = mapped_column(
        Enum(VideoStatus, name="video_status"), nullable=False, default=VideoStatus.PROCESSING
    )
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    processing_stage: Mapped[str] = mapped_column(String(64), nullable=False, default="queued")
    processing_total_chunks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    processing_completed_chunks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    processing_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
