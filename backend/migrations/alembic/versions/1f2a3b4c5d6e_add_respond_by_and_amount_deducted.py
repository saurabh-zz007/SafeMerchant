"""add_respond_by_and_amount_deducted

Revision ID: 1f2a3b4c5d6e
Revises: f45be9d97c97
Create Date: 2026-09-02 17:25:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1f2a3b4c5d6e'
down_revision: Union[str, Sequence[str], None] = 'f45be9d97c97'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add respond_by and amount_deducted to disputes table."""
    op.add_column(
        'disputes',
        sa.Column(
            'respond_by',
            sa.DateTime(timezone=True),
            nullable=True,
            comment='Dispute response deadline (from Razorpay respond_by timestamp)',
        ),
    )
    op.add_column(
        'disputes',
        sa.Column(
            'amount_deducted',
            sa.Integer(),
            server_default='0',
            nullable=True,
            comment='Amount deducted in paise (from Razorpay dispute entity)',
        ),
    )


def downgrade() -> None:
    """Drop respond_by and amount_deducted from disputes table."""
    op.drop_column('disputes', 'amount_deducted')
    op.drop_column('disputes', 'respond_by')
