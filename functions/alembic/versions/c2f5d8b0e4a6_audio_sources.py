"""Song Merger Pro editor: YouTube tracks loaded for their waveform and preview."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "c2f5d8b0e4a6"
down_revision = "b1e4c7a9d3f5"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("audio_sources",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True)),
        sa.Column("guest_key", sa.String(64)),
        sa.Column("video_id", sa.String(16), nullable=False),
        sa.Column("url", sa.String(500), nullable=False),
        sa.Column("title", sa.String(300)),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("error_code", sa.String(50)),
        sa.Column("duration_seconds", sa.Integer()),
        sa.Column("peaks", JSONB()),
        sa.Column("preview_object", sa.String(250)),
        sa.Column("original_object", sa.String(250)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("(user_id IS NULL) <> (guest_key IS NULL)", name="ck_audio_source_one_owner"))
    op.create_index("ix_audio_sources_user_id", "audio_sources", ["user_id"])
    op.create_index("ix_audio_sources_guest_key", "audio_sources", ["guest_key"])
    op.create_index("ix_audio_sources_expires_at", "audio_sources", ["expires_at"])


def downgrade():
    op.drop_table("audio_sources")
