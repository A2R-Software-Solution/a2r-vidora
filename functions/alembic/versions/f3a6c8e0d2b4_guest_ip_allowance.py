"""Shared per-IP daily allowance for guest devices."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "f3a6c8e0d2b4"
down_revision = "e2f5a7c9b1d3"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("videos", sa.Column("guest_cap_key", sa.String(64), nullable=True))
    op.add_column("credit_reservations", sa.Column(
        "cap_account_id", UUID(as_uuid=True), sa.ForeignKey("credit_accounts.id"), nullable=True))


def downgrade():
    op.drop_column("credit_reservations", "cap_account_id")
    op.drop_column("videos", "guest_cap_key")
