"""add safe processing progress fields to videos

Revision ID: 2d7b9a6c4e10
Revises: 6c10a9e721df
"""
from alembic import op
import sqlalchemy as sa

revision = "2d7b9a6c4e10"
down_revision = "6c10a9e721df"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("videos", sa.Column("processing_stage", sa.String(64), nullable=False, server_default="queued"))
    op.add_column("videos", sa.Column("processing_total_chunks", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("videos", sa.Column("processing_completed_chunks", sa.Integer(), nullable=False, server_default="0"))


def downgrade():
    op.drop_column("videos", "processing_completed_chunks")
    op.drop_column("videos", "processing_total_chunks")
    op.drop_column("videos", "processing_stage")
