"""Shared atomic request budgets across function instances."""
from alembic import op
import sqlalchemy as sa

revision = "6c10a9e721df"
down_revision = "5a08b732d74f"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "rate_limit_buckets",
        sa.Column("scope_key", sa.String(64), primary_key=True),
        sa.Column("window_start", sa.BigInteger(), primary_key=True),
        sa.Column("requests", sa.Integer(), nullable=False),
    )
    op.create_index("ix_rate_limit_buckets_window_start", "rate_limit_buckets", ["window_start"])


def downgrade():
    op.drop_index("ix_rate_limit_buckets_window_start", table_name="rate_limit_buckets")
    op.drop_table("rate_limit_buckets")
