"""
Unit tests for the webhook ingestion endpoint, HMAC-SHA256 signature verification, and idempotency checks.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.core.config import settings
from app.dispute.models import Dispute

pytestmark = pytest.mark.anyio


def _build_valid_payload() -> dict:
    now_ts = int(time.time())
    return {
        "entity": "event",
        "account_id": "acc_CFvOKjkTwf3GQy",
        "event": "payment.dispute.created",
        "contains": ["payment", "dispute"],
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_EFtmUsbwpXwBHI",
                    "entity": "payment",
                    "amount": 5297600,
                    "currency": "INR",
                    "base_amount": 5297600,
                    "status": "captured",
                    "order_id": "order_EFtkA6f5jdkfud",
                    "email": "gaurav.kumar@example.com",
                    "contact": "+919900000000",
                    "method": "card",
                    "amount_refunded": 0,
                    "created_at": now_ts - 86400,
                }
            },
            "dispute": {
                "entity": {
                    "id": "disp_EsIAlDcoUr8CaQ",
                    "entity": "dispute",
                    "payment_id": "pay_EFtmUsbwpXwBHI",
                    "amount": 39000,
                    "currency": "INR",
                    "amount_deducted": 0,
                    "reason_code": "processed_invalid_expired_card",
                    "respond_by": now_ts + 86400 * 5,
                    "status": "open",
                    "evidence": {
                        "amount": 39000,
                        "summary": None,
                        "shipping_proof": None,
                        "billing_proof": None,
                        "cancellation_proof": None,
                        "customer_communication": None,
                        "proof_of_service": None,
                        "explanation_letter": None,
                        "refund_confirmation": None,
                        "access_activity_log": None,
                        "refund_cancellation_policy": None,
                        "term_and_conditions": None,
                        "others": None,
                        "submitted_at": None,
                    },
                    "phase": "chargeback",
                    "created_at": now_ts,
                }
            }
        },
        "created_at": now_ts,
    }


def _sign_payload(payload_bytes: bytes, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()


@patch("app.dispute.routes.metrics_service.on_dispute_ingested", new_callable=AsyncMock)
@patch("app.dispute.routes.DisputeRepository")
@patch("app.dispute.routes.async_session_factory")
@patch("app.dispute.routes.process_dispute_and_broadcast", new_callable=AsyncMock)
@patch("app.dispute.routes._get_graph")
@patch("app.dispute.routes.manager.broadcast_system_event", new_callable=AsyncMock)
async def test_webhook_valid_signature(
    mock_broadcast,
    mock_get_graph,
    mock_process_task,
    mock_session_factory,
    mock_dispute_repo_cls,
    mock_metrics_ingested,
):
    mock_get_graph.return_value = MagicMock()
    mock_session = AsyncMock()
    mock_session_factory.return_value.__aenter__.return_value = mock_session
    mock_dispute = MagicMock(spec=Dispute)
    mock_dispute.id = "disp_EsIAlDcoUr8CaQ"
    mock_dispute.phase = "chargeback"
    mock_dispute.status = "processing"
    mock_dispute.document_id = None
    mock_repo = MagicMock()
    mock_repo.create_or_update_dispute = AsyncMock(return_value=(mock_dispute, True))
    mock_dispute_repo_cls.return_value = mock_repo

    payload = _build_valid_payload()
    payload_bytes = json.dumps(payload).encode("utf-8")
    sig = _sign_payload(payload_bytes, settings.razorpay_webhook_secret)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/webhook",
            content=payload_bytes,
            headers={
                "Content-Type": "application/json",
                "X-Razorpay-Signature": sig,
            },
        )

    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "accepted"
    assert data["dispute_id"] == "disp_EsIAlDcoUr8CaQ"
    mock_process_task.assert_called_once()


@patch("app.dispute.routes.process_dispute_and_broadcast", new_callable=AsyncMock)
@patch("app.dispute.routes.DisputeRepository")
@patch("app.dispute.routes.async_session_factory")
async def test_webhook_idempotency_already_processed_phase(
    mock_session_factory,
    mock_dispute_repo_cls,
    mock_process_task,
):
    """Verify webhook returns 200 OK and skips background graph if dispute is already in chargeback phase."""
    mock_session = AsyncMock()
    mock_session_factory.return_value.__aenter__.return_value = mock_session
    existing_dispute = MagicMock(spec=Dispute)
    existing_dispute.id = "disp_EsIAlDcoUr8CaQ"
    existing_dispute.phase = "chargeback"
    existing_dispute.document_id = None
    existing_dispute.status = "under_review"

    mock_repo = MagicMock()
    mock_repo.create_or_update_dispute = AsyncMock(return_value=(existing_dispute, False))
    mock_dispute_repo_cls.return_value = mock_repo

    payload = _build_valid_payload()
    payload_bytes = json.dumps(payload).encode("utf-8")
    sig = _sign_payload(payload_bytes, settings.razorpay_webhook_secret)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/webhook",
            content=payload_bytes,
            headers={
                "Content-Type": "application/json",
                "X-Razorpay-Signature": sig,
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "already_processed"
    assert data["message"] == "Dispute already processed"
    assert data["dispute_id"] == "disp_EsIAlDcoUr8CaQ"
    mock_process_task.assert_not_called()


@patch("app.dispute.routes.process_dispute_and_broadcast", new_callable=AsyncMock)
@patch("app.dispute.routes.DisputeRepository")
@patch("app.dispute.routes.async_session_factory")
async def test_webhook_idempotency_already_processed_document_id(
    mock_session_factory,
    mock_dispute_repo_cls,
    mock_process_task,
):
    """Verify webhook returns 200 OK and skips background graph if dispute already has document_id."""
    mock_session = AsyncMock()
    mock_session_factory.return_value.__aenter__.return_value = mock_session
    existing_dispute = MagicMock(spec=Dispute)
    existing_dispute.id = "disp_EsIAlDcoUr8CaQ"
    existing_dispute.phase = "fraud"
    existing_dispute.document_id = "doc_ABC123456"
    existing_dispute.status = "resolved"

    mock_repo = MagicMock()
    mock_repo.create_or_update_dispute = AsyncMock(return_value=(existing_dispute, False))
    mock_dispute_repo_cls.return_value = mock_repo

    payload = _build_valid_payload()
    payload_bytes = json.dumps(payload).encode("utf-8")
    sig = _sign_payload(payload_bytes, settings.razorpay_webhook_secret)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/webhook",
            content=payload_bytes,
            headers={
                "Content-Type": "application/json",
                "X-Razorpay-Signature": sig,
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "already_processed"
    assert data["message"] == "Dispute already processed"
    assert data["dispute_id"] == "disp_EsIAlDcoUr8CaQ"
    mock_process_task.assert_not_called()


async def test_webhook_missing_signature():
    payload = _build_valid_payload()
    payload_bytes = json.dumps(payload).encode("utf-8")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/webhook",
            content=payload_bytes,
            headers={"Content-Type": "application/json"},
        )

    assert response.status_code == 400
    assert "Missing X-Razorpay-Signature" in response.json()["detail"]


async def test_webhook_invalid_signature():
    payload = _build_valid_payload()
    payload_bytes = json.dumps(payload).encode("utf-8")
    fake_sig = "a" * 64

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/webhook",
            content=payload_bytes,
            headers={
                "Content-Type": "application/json",
                "X-Razorpay-Signature": fake_sig,
            },
        )

    assert response.status_code == 400
    assert "Invalid webhook signature" in response.json()["detail"]


async def test_webhook_malformed_json():
    bad_bytes = b"not-a-valid-json{"
    sig = _sign_payload(bad_bytes, settings.razorpay_webhook_secret)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/webhook",
            content=bad_bytes,
            headers={
                "Content-Type": "application/json",
                "X-Razorpay-Signature": sig,
            },
        )

    assert response.status_code == 400
    assert "Malformed webhook payload" in response.json()["detail"]


async def test_webhook_unsupported_event():
    payload = _build_valid_payload()
    payload["event"] = "payment.captured"
    payload_bytes = json.dumps(payload).encode("utf-8")
    sig = _sign_payload(payload_bytes, settings.razorpay_webhook_secret)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/webhook",
            content=payload_bytes,
            headers={
                "Content-Type": "application/json",
                "X-Razorpay-Signature": sig,
            },
        )

    assert response.status_code == 400
    assert "Unsupported event type" in response.json()["detail"]
