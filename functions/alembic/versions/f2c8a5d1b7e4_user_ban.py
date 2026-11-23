"""Admins can ban a user and give a reason, which the user sees."""
from alembic import op
import sqlalchemy as sa

revision = "f2c8a5d1b7e4"
down_revision = "e9b4c2d7a1f3"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("banned_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("ban_reason", sa.String(300), nullable=True))


def downgrade():
    op.drop_column("users", "ban_reason")
    op.drop_column("users", "banned_at")
