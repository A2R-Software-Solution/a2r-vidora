"""Admin flag on users. Set it by hand: UPDATE users SET is_admin = true WHERE email = '...'."""
from alembic import op
import sqlalchemy as sa

revision = "b7c2d9e4a1f6"
down_revision = "a8d1e4f7c2b5"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade():
    op.drop_column("users", "is_admin")
