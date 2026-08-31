"""add_dispute_submission_log_table

Revision ID: a2a846db9566
Revises: 03a422b927ce
Create Date: 2026-08-31 14:24:27.940398

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a2a846db9566'
down_revision: Union[str, Sequence[str], None] = '03a422b927ce'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the dispute_submission_log table for tracking outbound API payloads."""
    op.create_table(
        'dispute_submission_log',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('dispute_id', sa.String(length=100), sa.ForeignKey('disputes.id', ondelete='CASCADE'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('document_id', sa.String(length=100), nullable=True),
        sa.Column('document_upload_payload', sa.JSON(), nullable=True),
        sa.Column('document_upload_status', sa.Integer(), nullable=True),
        sa.Column('document_upload_response', sa.JSON(), nullable=True),
        sa.Column('contest_payload', sa.JSON(), nullable=True),
        sa.Column('contest_status', sa.Integer(), nullable=True),
        sa.Column('contest_response', sa.JSON(), nullable=True),
        sa.Column('outcome', sa.String(length=50), nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_dispute_submission_log_dispute_id', 'dispute_submission_log', ['dispute_id'])


def downgrade() -> None:
    """Drop the dispute_submission_log table."""
    op.drop_index('idx_dispute_submission_log_dispute_id', table_name='dispute_submission_log')
    op.drop_table('dispute_submission_log')

