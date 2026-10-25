"""Song Merger jobs."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "d5e9a3b7c1f8"
down_revision = "b7c2d9e4a1f6"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("audio_merges",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True)),
        sa.Column("guest_key", sa.String(64)),
        sa.Column("guest_cap_key", sa.String(64)),
        sa.Column("tracks", JSONB(), nullable=False),
        sa.Column("output_format", sa.String(8), nullable=False),
        sa.Column("crossfade_seconds", sa.Integer(), nullable=False),
        sa.Column("total_seconds", sa.Integer(), nullable=False),
        sa.Column("credit_cost", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("attempt_id", UUID(as_uuid=True), nullable=False),
        sa.Column("object_name", sa.String(250)),
        sa.Column("error_code", sa.String(50)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("(user_id IS NULL) <> (guest_key IS NULL)", name="ck_audio_merge_one_owner"))
    op.create_index("ix_audio_merges_user_id", "audio_merges", ["user_id"])
    op.create_index("ix_audio_merges_guest_key", "audio_merges", ["guest_key"])
    op.create_index("ix_audio_merges_expires_at", "audio_merges", ["expires_at"])


def downgrade():
    op.drop_table("audio_merges")
