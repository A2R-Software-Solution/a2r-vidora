"""Settings an admin can change from the admin panel without a deploy."""
from alembic import op
import sqlalchemy as sa

revision = "b1e4c7a9d3f5"
down_revision = "a3d8f2b6c4e1"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("value", sa.Integer(), nullable=False),
        sa.Column("updated_by", sa.String(320), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade():
    op.drop_table("app_settings")
