"""add search_vector for hybrid search

Revision ID: 5a08b732d74f
Revises: 73c2327c654b
Create Date: 2026-08-21 08:35:48.873680

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '5a08b732d74f'
down_revision: Union[str, Sequence[str], None] = '73c2327c654b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('transcript_chunks', sa.Column('search_vector', postgresql.TSVECTOR(), sa.Computed("to_tsvector('english', chunk_text)", persisted=True), nullable=False))
    op.create_index(
        'ix_transcript_chunks_search_vector',
        'transcript_chunks',
        ['search_vector'],
        postgresql_using='gin',
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_transcript_chunks_search_vector', table_name='transcript_chunks')
    op.drop_column('transcript_chunks', 'search_vector')
