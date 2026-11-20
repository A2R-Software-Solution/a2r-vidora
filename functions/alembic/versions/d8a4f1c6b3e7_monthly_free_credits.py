"""Free credits become a monthly allowance for signed-in users; guests get none.

daily_free_used becomes free_used, counted per IST calendar month (free_month).
The question counters stay daily. Guest admin settings are removed and the
user allowance setting is renamed to user_monthly_credits.
"""
from alembic import op
import sqlalchemy as sa

revision = "d8a4f1c6b3e7"
down_revision = "c2f5d8b0e4a6"
branch_labels = None
depends_on = None

GUEST_KEYS = "('guest_daily_credits', 'guest_ip_daily_credits', 'guest_daily_questions', 'guest_ip_daily_questions')"


def upgrade():
    op.drop_constraint("ck_credit_account_daily", "credit_accounts", type_="check")
    op.alter_column("credit_accounts", "daily_free_used", new_column_name="free_used")
    op.add_column("credit_accounts", sa.Column("free_month", sa.Date(), nullable=True))
    # Today's usage counts toward the current month.
    op.execute("UPDATE credit_accounts SET free_month = date_trunc('month', daily_date)::date")
    op.alter_column("credit_accounts", "free_month", nullable=False)
    op.create_check_constraint("ck_credit_account_counters", "credit_accounts",
        "free_used >= 0 AND daily_chat_used >= 0")
    op.execute(f"DELETE FROM app_settings WHERE key IN {GUEST_KEYS}")
    op.execute("UPDATE app_settings SET key = 'user_monthly_credits' WHERE key = 'user_daily_credits'")


def downgrade():
    op.execute("UPDATE app_settings SET key = 'user_daily_credits' WHERE key = 'user_monthly_credits'")
    op.drop_constraint("ck_credit_account_counters", "credit_accounts", type_="check")
    op.drop_column("credit_accounts", "free_month")
    op.alter_column("credit_accounts", "free_used", new_column_name="daily_free_used")
    op.create_check_constraint("ck_credit_account_daily", "credit_accounts",
        "daily_free_used >= 0 AND daily_chat_used >= 0")
