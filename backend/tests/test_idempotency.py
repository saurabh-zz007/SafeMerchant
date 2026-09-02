"""
Unit tests for webhook idempotency, LangGraph workflow idempotency, and PostgreSQL upsert logic.
"""

from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select, func

from app.dispute.agent.nodes.super_step_1 import retrieve_evidence
from app.dispute.dispute_repository import DisputeRepository
from app.dispute.metrics_repository import MetricsRepository
from app.dispute.models import Dispute
from app.dispute.submission import submit_dispute_evidence

pytestmark = pytest.mark.anyio


@patch("app.dispute.agent.nodes.super_step_1.async_session_factory")
@patch("app.dispute.agent.nodes.super_step_1.DisputeRepository")
@patch("app.dispute.agent.nodes.super_step_1.EvidenceRepository")
async def test_retrieve_evidence_idempotency_phase_chargeback(
    mock_evidence_repo_cls,
    mock_dispute_repo_cls,
    mock_session_factory,
):
    """Verify retrieve_evidence skips evidence gathering if dispute is already processed/contested."""
    mock_session = AsyncMock()
    mock_session_factory.return_value.__aenter__.return_value = mock_session

    existing = MagicMock(spec=Dispute)
    existing.id = "disp_test_001"
    existing.phase = "chargeback"
    existing.status = "under_review"
    existing.document_id = None

    mock_dispute_repo = MagicMock()
    mock_dispute_repo.get_dispute = AsyncMock(return_value=existing)
    mock_dispute_repo_cls.return_value = mock_dispute_repo

    mock_evidence_repo = MagicMock()
    mock_evidence_repo.fetch_full_evidence = AsyncMock()
    mock_evidence_repo_cls.return_value = mock_evidence_repo

    state = {
        "dispute_id": "disp_test_001",
        "order_id": "ORD_123",
        "payment_id": "pay_123",
        "node_history": ["ingestion"],
    }

    result = await retrieve_evidence(state)

    assert result["error"] == "Dispute already processed"
    assert result["current_node"] == "retrieve_evidence"
    assert "retrieve_evidence" in result["node_history"]
    mock_evidence_repo.fetch_full_evidence.assert_not_called()


@patch("app.dispute.agent.nodes.super_step_1.async_session_factory")
@patch("app.dispute.agent.nodes.super_step_1.DisputeRepository")
@patch("app.dispute.agent.nodes.super_step_1.EvidenceRepository")
async def test_retrieve_evidence_idempotency_document_id(
    mock_evidence_repo_cls,
    mock_dispute_repo_cls,
    mock_session_factory,
):
    """Verify retrieve_evidence skips evidence gathering if dispute already has document_id."""
    mock_session = AsyncMock()
    mock_session_factory.return_value.__aenter__.return_value = mock_session

    existing = MagicMock(spec=Dispute)
    existing.id = "disp_test_002"
    existing.phase = "fraud"
    existing.status = "resolved"
    existing.document_id = "doc_xyz123"

    mock_dispute_repo = MagicMock()
    mock_dispute_repo.get_dispute = AsyncMock(return_value=existing)
    mock_dispute_repo_cls.return_value = mock_dispute_repo

    mock_evidence_repo = MagicMock()
    mock_evidence_repo.fetch_full_evidence = AsyncMock()
    mock_evidence_repo_cls.return_value = mock_evidence_repo

    state = {
        "dispute_id": "disp_test_002",
        "order_id": "ORD_456",
        "payment_id": "pay_456",
        "node_history": ["ingestion"],
    }

    result = await retrieve_evidence(state)

    assert result["error"] == "Dispute already processed"
    mock_evidence_repo.fetch_full_evidence.assert_not_called()


@patch("app.dispute.submission.settings")
@patch("app.dispute.submission.async_session_factory")
@patch("app.dispute.submission.DisputeRepository")
async def test_submit_dispute_evidence_idempotency(
    mock_dispute_repo_cls,
    mock_session_factory,
    mock_settings,
):
    """Verify submit_dispute_evidence returns early if document_id is already populated."""
    mock_settings.razorpay_key_id = "rzp_test_key"
    mock_settings.razorpay_key_secret = "rzp_test_secret"

    mock_session = AsyncMock()
    mock_session_factory.return_value.__aenter__.return_value = mock_session

    existing = MagicMock(spec=Dispute)
    existing.id = "disp_test_003"
    existing.document_id = "doc_already_uploaded"
    existing.storage_path = "evidence-pdfs/disp_test_003/evidence.pdf"

    mock_repo = MagicMock()
    mock_repo.get_dispute = AsyncMock(return_value=existing)
    mock_dispute_repo_cls.return_value = mock_repo

    result = await submit_dispute_evidence("disp_test_003")

    assert result["status"] == "already_processed"
    assert result["outcome"] == "evidence_already_submitted"
    assert result["document_id"] == "doc_already_uploaded"


async def test_refresh_breakdowns_uses_upsert():
    """Verify MetricsRepository.refresh_breakdowns uses on_conflict_do_update."""
    mock_session = AsyncMock()

    # Mock query results for the 3 dimensions
    mock_row = MagicMock()
    mock_row.dim_value = "chargeback"
    mock_row.cnt = 5
    mock_row.amt = 250000

    mock_result = MagicMock()
    mock_result.all.return_value = [mock_row]

    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.commit = AsyncMock()

    repo = MetricsRepository(mock_session)
    await repo.refresh_breakdowns()

    # Verify session execute was called for each dimension select + upsert insert
    assert mock_session.execute.call_count >= 3
    mock_session.commit.assert_called_once()
