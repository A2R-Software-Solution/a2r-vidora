"""Allow Song Merger credit reservations."""
from alembic import op

revision = "e6f1b4c8d2a9"
down_revision = "d5e9a3b7c1f8"
branch_labels = None
depends_on = None

NAME = "ck_credit_reservation_source"


def upgrade():
    op.drop_constraint(NAME, "credit_reservations", type_="check")
    op.create_check_constraint(NAME, "credit_reservations", "source_type IN ('video', 'short', 'audio_merge')")


def downgrade():
    # Fails while audio_merge reservations exist; refund or delete them first.
    op.drop_constraint(NAME, "credit_reservations", type_="check")
    op.create_check_constraint(NAME, "credit_reservations", "source_type IN ('video', 'short')")
