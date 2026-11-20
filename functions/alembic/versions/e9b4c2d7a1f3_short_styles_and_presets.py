"""Shorts can be rendered in a chosen look (ratio, background, caption style, edited
captions), so one clip may have several renders; users can save caption presets."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "e9b4c2d7a1f3"
down_revision = "d8a4f1c6b3e7"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("shorts", sa.Column("options", JSONB(), nullable=True))
    op.add_column("shorts", sa.Column("options_hash", sa.String(64), nullable=False, server_default=""))
    op.drop_constraint("uq_short_range", "shorts", type_="unique")
    op.create_unique_constraint("uq_short_render", "shorts", ["video_id", "start_time", "end_time", "options_hash"])
    op.create_table("short_presets",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(40), nullable=False),
        sa.Column("style", JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", "name", name="uq_short_preset_name"))
    op.create_index("ix_short_presets_user_id", "short_presets", ["user_id"])


def downgrade():
    op.drop_table("short_presets")
    op.drop_constraint("uq_short_render", "shorts", type_="unique")
    # The old schema allows one job per range: keep the oldest render of each.
    op.execute("""DELETE FROM shorts a USING shorts b
                  WHERE a.video_id = b.video_id AND a.start_time = b.start_time AND a.end_time = b.end_time
                    AND (a.created_at, a.id) > (b.created_at, b.id)""")
    op.create_unique_constraint("uq_short_range", "shorts", ["video_id", "start_time", "end_time"])
    op.drop_column("shorts", "options_hash")
    op.drop_column("shorts", "options")
