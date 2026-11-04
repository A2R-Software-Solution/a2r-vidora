"""Downloads are paid from the normal credits, so drop the separate download allowance."""
from alembic import op
import sqlalchemy as sa

revision = "a3d8f2b6c4e1"
down_revision = "f9c1d7e3a5b2"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint("ck_credit_reservation_allowance", "credit_reservations", type_="check")
    op.drop_column("credit_reservations", "allowance")
    op.drop_constraint("ck_credit_account_daily", "credit_accounts", type_="check")
    op.create_check_constraint("ck_credit_account_daily", "credit_accounts",
        "daily_free_used >= 0 AND daily_chat_used >= 0")
    op.drop_column("credit_accounts", "daily_download_used")


def downgrade():
    op.add_column("credit_accounts", sa.Column(
        "daily_download_used", sa.Integer(), nullable=False, server_default="0"))
    op.drop_constraint("ck_credit_account_daily", "credit_accounts", type_="check")
    op.create_check_constraint("ck_credit_account_daily", "credit_accounts",
        "daily_free_used >= 0 AND daily_chat_used >= 0 AND daily_download_used >= 0")
    op.add_column("credit_reservations", sa.Column(
        "allowance", sa.String(10), nullable=False, server_default="analysis"))
    op.create_check_constraint("ck_credit_reservation_allowance", "credit_reservations",
        "allowance IN ('analysis', 'download')")
