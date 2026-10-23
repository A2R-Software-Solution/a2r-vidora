"""Mark videos submitted by paying accounts for the priority lane."""
from alembic import op
import sqlalchemy as sa

revision = "a8d1e4f7c2b5"
down_revision = "f3a6c8e0d2b4"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("videos", sa.Column("priority", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade():
    op.drop_column("videos", "priority")
