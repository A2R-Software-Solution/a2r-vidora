"""Shared Groq STT quota reservations.

Revision ID: 9f4e216bd8a1
Revises: 2d7b9a6c4e10
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "9f4e216bd8a1"
down_revision = "2d7b9a6c4e10"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("videos", sa.Column("processing_updated_at", sa.DateTime(timezone=True),
                                      nullable=False, server_default=sa.func.now()))
    op.create_table("stt_quota_reservations",
                    sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
                    sa.Column("reserved_at", sa.DateTime(timezone=True), nullable=False),
                    sa.Column("audio_seconds", sa.Integer(), nullable=False))
    op.create_index("ix_stt_quota_reservations_reserved_at", "stt_quota_reservations", ["reserved_at"])
    op.create_table("stt_request_checkpoints",
                    sa.Column("video_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("videos.id", ondelete="CASCADE"), nullable=False),
                    sa.Column("first_sequence", sa.Integer(), nullable=False),
                    sa.Column("audio_sha256", sa.String(64), nullable=False),
                    sa.Column("segments", postgresql.JSONB(), nullable=False),
                    sa.PrimaryKeyConstraint("video_id", "first_sequence"))


def downgrade():
    op.drop_table("stt_request_checkpoints")
    op.drop_index("ix_stt_quota_reservations_reserved_at", table_name="stt_quota_reservations")
    op.drop_table("stt_quota_reservations")
    op.drop_column("videos", "processing_updated_at")
