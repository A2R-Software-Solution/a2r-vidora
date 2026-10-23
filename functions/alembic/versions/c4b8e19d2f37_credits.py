"""Credit accounts, reservations, payments and ledger."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "c4b8e19d2f37"
down_revision = "a3e71f20b691"
branch_labels = None
depends_on = None


def _timestamps():
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def upgrade():
    op.create_table("credit_accounts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), unique=True),
        sa.Column("guest_key", sa.String(64), unique=True),
        sa.Column("purchased_balance", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("daily_free_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("daily_chat_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("daily_date", sa.Date(), nullable=False),
        *_timestamps(),
        sa.CheckConstraint("(user_id IS NULL) <> (guest_key IS NULL)", name="ck_credit_account_owner"),
        sa.CheckConstraint("purchased_balance >= 0", name="ck_credit_account_balance"),
        sa.CheckConstraint("daily_free_used >= 0 AND daily_chat_used >= 0", name="ck_credit_account_daily"))

    op.create_table("credit_reservations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("account_id", UUID(as_uuid=True), sa.ForeignKey("credit_accounts.id"), nullable=False),
        sa.Column("source_type", sa.String(20), nullable=False),
        sa.Column("source_id", UUID(as_uuid=True), nullable=False),
        sa.Column("idempotency_key", sa.String(120), nullable=False, unique=True),
        sa.Column("free_amount", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("purchased_amount", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(20), nullable=False, server_default="held"),
        *_timestamps(),
        sa.CheckConstraint("source_type IN ('video', 'short')", name="ck_credit_reservation_source"),
        sa.CheckConstraint("status IN ('held', 'settled', 'released')", name="ck_credit_reservation_status"),
        sa.CheckConstraint("free_amount >= 0 AND purchased_amount >= 0 AND free_amount + purchased_amount > 0",
                           name="ck_credit_reservation_amounts"))
    op.create_index("ix_credit_reservations_account_id", "credit_reservations", ["account_id"])
    op.create_index("ix_credit_reservations_source_id", "credit_reservations", ["source_id"])
    op.create_index("ix_credit_reservations_status_created", "credit_reservations", ["status", "created_at"])

    op.create_table("payments",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("pack_code", sa.String(20), nullable=False),
        sa.Column("credits", sa.Integer(), nullable=False),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="USD"),
        sa.Column("provider", sa.String(20), nullable=False),
        sa.Column("provider_order_id", sa.String(100), nullable=False, unique=True),
        sa.Column("provider_payment_id", sa.String(100), unique=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="created"),
        *_timestamps(),
        sa.Column("paid_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("status IN ('created', 'paid', 'failed', 'refunded', 'disputed')",
                           name="ck_payment_status"),
        sa.CheckConstraint("credits > 0 AND amount_cents > 0", name="ck_payment_amounts"))
    op.create_index("ix_payments_user_id", "payments", ["user_id"])

    op.create_table("credit_ledger",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("account_id", UUID(as_uuid=True), sa.ForeignKey("credit_accounts.id"), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("bucket", sa.String(10), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("reservation_id", UUID(as_uuid=True), sa.ForeignKey("credit_reservations.id")),
        sa.Column("payment_id", UUID(as_uuid=True), sa.ForeignKey("payments.id")),
        sa.Column("purchased_balance_after", sa.Integer(), nullable=False),
        sa.Column("note", sa.String(250)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("kind IN ('reserve', 'release', 'purchase', 'refund', 'adjust')",
                           name="ck_credit_ledger_kind"),
        sa.CheckConstraint("bucket IN ('free', 'purchased')", name="ck_credit_ledger_bucket"),
        sa.CheckConstraint("amount <> 0", name="ck_credit_ledger_amount"))
    op.create_index("ix_credit_ledger_account_id", "credit_ledger", ["account_id"])
    op.create_index("uq_credit_ledger_reservation_once", "credit_ledger", ["reservation_id", "kind", "bucket"],
                    unique=True, postgresql_where=sa.text("reservation_id IS NOT NULL"))
    op.create_index("uq_credit_ledger_payment_once", "credit_ledger", ["payment_id", "kind"],
                    unique=True, postgresql_where=sa.text("payment_id IS NOT NULL"))


def downgrade():
    op.drop_table("credit_ledger")
    op.drop_table("payments")
    op.drop_table("credit_reservations")
    op.drop_table("credit_accounts")
