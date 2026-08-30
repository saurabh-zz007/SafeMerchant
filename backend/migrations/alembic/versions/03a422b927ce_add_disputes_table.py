"""add_disputes_table

Revision ID: 03a422b927ce
Revises: 
Create Date: 2026-08-29 19:07:28.908426

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '03a422b927ce'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the disputes table for HITL lifecycle tracking."""
    op.create_table('disputes',
        sa.Column('id', sa.String(length=100), nullable=False, comment='Razorpay dispute ID (e.g., disp_XXXX)'),
        sa.Column('status', sa.String(length=50), server_default='processing', nullable=False, comment='processing | awaiting_review | resolved | error'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('history', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False, comment='Chronological log: webhook payload, node outcomes, review decisions'),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    """Drop the disputes table."""
    op.drop_table('disputes')
