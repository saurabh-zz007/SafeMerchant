"""add_storage_path_and_evidence_jobs

Revision ID: f45be9d97c97
Revises: 84529e4c8579
Create Date: 2026-08-31 22:16:09.593898

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f45be9d97c97'
down_revision: Union[str, Sequence[str], None] = '84529e4c8579'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'disputes',
        sa.Column(
            'storage_path',
            sa.String(length=255),
            nullable=True,
            comment='Supabase Storage path (e.g., evidence-pdfs/disp_XXXX/evidence.pdf)',
        ),
    )
    op.create_table(
        'evidence_jobs',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('dispute_id', sa.String(length=100), sa.ForeignKey('disputes.id', ondelete='CASCADE'), nullable=False),
        sa.Column('status', sa.String(length=30), server_default='queued', nullable=False),
        sa.Column('attempts', sa.Integer(), server_default='0', nullable=False),
        sa.Column('max_attempts', sa.Integer(), server_default='3', nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_evidence_jobs_dispute_id', 'evidence_jobs', ['dispute_id'])
    op.create_index('idx_evidence_jobs_status', 'evidence_jobs', ['status'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('idx_evidence_jobs_status', table_name='evidence_jobs')
    op.drop_index('idx_evidence_jobs_dispute_id', table_name='evidence_jobs')
    op.drop_table('evidence_jobs')
    op.drop_column('disputes', 'storage_path')
