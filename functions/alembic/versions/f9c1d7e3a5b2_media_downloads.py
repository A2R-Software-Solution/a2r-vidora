"""Media Downloader jobs and its own daily credit allowance."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "f9c1d7e3a5b2"
down_revision = "e6f1b4c8d2a9"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("credit_accounts", sa.Column(
        "daily_download_used", sa.Integer(), nullable=False, server_default="0"))
    op.drop_constraint("ck_credit_account_daily", "credit_accounts", type_="check")
    op.create_check_constraint("ck_credit_account_daily", "credit_accounts",
        "daily_free_used >= 0 AND daily_chat_used >= 0 AND daily_download_used >= 0")

    op.add_column("credit_reservations", sa.Column(
        "allowance", sa.String(10), nullable=False, server_default="analysis"))
    op.create_check_constraint("ck_credit_reservation_allowance", "credit_reservations",
        "allowance IN ('analysis', 'download')")
    op.drop_constraint("ck_credit_reservation_source", "credit_reservations", type_="check")
    op.create_check_constraint("ck_credit_reservation_source", "credit_reservations",
        "source_type IN ('video', 'short', 'audio_merge', 'download')")

    op.create_table("media_downloads",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True)),
        sa.Column("guest_key", sa.String(64)),
        sa.Column("guest_cap_key", sa.String(64)),
        sa.Column("source_url", sa.String(500), nullable=False),
        sa.Column("title", sa.String(300)),
        sa.Column("quality", sa.String(16), nullable=False),
        sa.Column("duration_seconds", sa.Integer(), nullable=False),
        sa.Column("credit_cost", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("attempt_id", UUID(as_uuid=True), nullable=False),
        sa.Column("object_name", sa.String(250)),
        sa.Column("error_code", sa.String(50)),
        sa.Column("rights_confirmed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("(user_id IS NULL) <> (guest_key IS NULL)", name="ck_media_download_one_owner"))
    op.create_index("ix_media_downloads_user_id", "media_downloads", ["user_id"])
    op.create_index("ix_media_downloads_guest_key", "media_downloads", ["guest_key"])
    op.create_index("ix_media_downloads_expires_at", "media_downloads", ["expires_at"])


def downgrade():
    # Fails while download reservations or jobs exist; refund or delete them first.
    op.drop_table("media_downloads")
    op.drop_constraint("ck_credit_reservation_source", "credit_reservations", type_="check")
    op.create_check_constraint("ck_credit_reservation_source", "credit_reservations",
        "source_type IN ('video', 'short', 'audio_merge')")
    op.drop_constraint("ck_credit_reservation_allowance", "credit_reservations", type_="check")
    op.drop_column("credit_reservations", "allowance")
    op.drop_constraint("ck_credit_account_daily", "credit_accounts", type_="check")
    op.create_check_constraint("ck_credit_account_daily", "credit_accounts",
        "daily_free_used >= 0 AND daily_chat_used >= 0")
    op.drop_column("credit_accounts", "daily_download_used")
