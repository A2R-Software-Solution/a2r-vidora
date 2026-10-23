"""Record the guest credit wallet that submitted a video."""
from alembic import op
import sqlalchemy as sa

revision = "e2f5a7c9b1d3"
down_revision = "c4b8e19d2f37"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("videos", sa.Column("guest_key", sa.String(64), nullable=True))


def downgrade():
    op.drop_column("videos", "guest_key")
