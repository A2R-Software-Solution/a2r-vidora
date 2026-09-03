import uuid
from datetime import datetime

from sqlalchemy import Text, Numeric, DateTime, ForeignKey, func, Computed
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID, TSVECTOR
from pgvector.sqlalchemy import Vector

from app.db.base import Base


class TranscriptChunk(Base):
    __tablename__ = "transcript_chunks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    video_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("videos.id"), nullable=False
    )
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)
    start_time: Mapped[float] = mapped_column(Numeric, nullable=False)
    end_time: Mapped[float] = mapped_column(Numeric, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(384), nullable=False)
    search_vector: Mapped[str] = mapped_column(
        TSVECTOR, Computed("to_tsvector('english', chunk_text)", persisted=True)
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )