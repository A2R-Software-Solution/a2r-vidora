"""Coupon codes, and the coupon each payment used."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "c7e2a9f4b1d6"
down_revision = "f2c8a5d1b7e4"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "coupons",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(40), nullable=False, unique=True),
        sa.Column("percent_off", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("bonus_credits", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("packs", sa.String(60), nullable=True),
        sa.Column("currency", sa.String(3), nullable=True),
        sa.Column("max_uses", sa.Integer(), nullable=True),
        sa.Column("per_user_limit", sa.Integer(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("note", sa.String(200), nullable=True),
        sa.Column("created_by", sa.String(320), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("percent_off BETWEEN 0 AND 100", name="ck_coupon_percent_off"),
        sa.CheckConstraint("bonus_credits >= 0", name="ck_coupon_bonus_credits"),
        sa.CheckConstraint("percent_off > 0 OR bonus_credits > 0", name="ck_coupon_has_benefit"),
        sa.CheckConstraint("max_uses IS NULL OR max_uses > 0", name="ck_coupon_max_uses"),
        sa.CheckConstraint("per_user_limit IS NULL OR per_user_limit > 0", name="ck_coupon_per_user_limit"),
        sa.CheckConstraint("currency IS NULL OR currency IN ('USD', 'INR')", name="ck_coupon_currency"),
    )
    op.add_column("payments", sa.Column("coupon_id", UUID(as_uuid=True), sa.ForeignKey("coupons.id"), nullable=True))
    op.add_column("payments", sa.Column("coupon_code", sa.String(40), nullable=True))
    op.create_index("ix_payments_coupon_id", "payments", ["coupon_id"])


def downgrade():
    op.drop_index("ix_payments_coupon_id", table_name="payments")
    op.drop_column("payments", "coupon_code")
    op.drop_column("payments", "coupon_id")
    op.drop_table("coupons")
