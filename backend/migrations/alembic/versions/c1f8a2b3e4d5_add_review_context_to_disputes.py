"""add_review_context_to_disputes

Revision ID: c1f8a2b3e4d5
Revises: f45be9d97c97
Create Date: 2026-09-03 16:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'c1f8a2b3e4d5'
down_revision: Union[str, Sequence[str], None] = '1f2a3b4c5d6e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema to add review_context JSONB column to disputes."""
    op.add_column(
        'disputes',
        sa.Column(
            'review_context',
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment='Persisted AI brief and triage context for HITL review',
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('disputes', 'review_context')
