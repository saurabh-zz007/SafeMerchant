"""add document_id to disputes

Revision ID: 84529e4c8579
Revises: a2a846db9566
Create Date: 2026-08-31 20:57:01.850221

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '84529e4c8579'
down_revision: Union[str, Sequence[str], None] = 'a2a846db9566'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('disputes', sa.Column('document_id', sa.String(length=100), nullable=True, comment='Razorpay document ID (e.g., doc_XXXX)'))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('disputes', 'document_id')
