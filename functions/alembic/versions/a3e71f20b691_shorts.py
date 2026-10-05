"""Short rendering jobs and quota reservations."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "a3e71f20b691"
down_revision = "9f4e216bd8a1"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("shorts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("video_id", UUID(as_uuid=True), sa.ForeignKey("videos.id"), nullable=False),
        sa.Column("start_time", sa.Integer(), nullable=False),
        sa.Column("end_time", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("attempt_id", UUID(as_uuid=True), nullable=False),
        sa.Column("object_name", sa.String(250)),
        sa.Column("error_code", sa.String(50)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("video_id", "start_time", "end_time", name="uq_short_range"),
        sa.CheckConstraint("start_time >= 0 AND end_time - start_time BETWEEN 20 AND 60", name="ck_short_range"))
    op.create_index("ix_shorts_video_id", "shorts", ["video_id"])


def downgrade():
    op.drop_table("shorts")
