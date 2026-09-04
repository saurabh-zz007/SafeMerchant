"""
Integration tests for the Strict "Defense-Only" Failsafe.

Verifies that when a dispute webhook arrives with an order_id or payment_id
that does NOT exist in the local PostgreSQL database:
1. The LangGraph AI Agent is immediately bypassed.
2. The dispute is routed to 'awaiting_review' (Manual Review) state.
3. The review_context clearly states that not enough data is available to solve the case.
4. Reviewers can manually resolve the dispute without crashing.
"""

from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core.db import async_session_factory, engine
from app.dispute.models import Dispute
from app.main import app
from app.dispute.schemas.review import ReviewDecision

pytestmark = pytest.mark.anyio


@pytest.fixture(autouse=True)
async def dispose_db_pool():
    yield
    await engine.dispose()


@patch("app.dispute.routes._get_graph")
@patch("app.dispute.routes.manager.broadcast_system_event", new_callable=AsyncMock)
async def test_defense_only_failsafe_missing_records(mock_broadcast, mock_get_graph):
    """Verify that an unmatched order/payment bypasses LangGraph and routes to manual review."""
    mock_get_graph.return_value = MagicMock()
    import hashlib
    import hmac
    import json
    import time
    from app.core.config import settings

    now_ts = int(time.time())
    dispute_id = f"disp_fail_{now_ts}"
    payment_id = f"pay_nonexistent_{now_ts}"
    order_id = f"ORD_NONEXISTENT_{now_ts}"

    webhook_payload = {
        "entity": "event",
        "account_id": "acc_CFvOKjkTwf3GQy",
        "event": "payment.dispute.created",
        "contains": ["payment", "dispute"],
        "payload": {
            "payment": {
                "entity": {
                    "id": payment_id,
                    "entity": "payment",
                    "amount": 499900,
                    "currency": "INR",
                    "base_amount": 499900,
                    "status": "captured",
                    "order_id": order_id,
                    "email": "unknown_buyer@example.com",
                    "contact": "+919876543210",
                    "method": "card",
                    "amount_refunded": 0,
                    "created_at": now_ts - 86400 * 5,
                }
            },
            "dispute": {
                "entity": {
                    "id": dispute_id,
                    "entity": "dispute",
                    "payment_id": payment_id,
                    "amount": 499900,
                    "currency": "INR",
                    "amount_deducted": 0,
                    "reason_code": "product_not_received",
                    "respond_by": now_ts + 86400 * 5,
                    "status": "open",
                    "phase": "chargeback",
                    "created_at": now_ts,
                }
            },
        },
        "created_at": now_ts,
    }

    payload_bytes = json.dumps(webhook_payload).encode("utf-8")
    secret = settings.razorpay_webhook_secret
    sig = hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        with patch("app.dispute.routes.process_dispute_and_broadcast", new_callable=AsyncMock):
            response = await client.post(
                "/api/v1/webhook",
                content=payload_bytes,
                headers={
                    "Content-Type": "application/json",
                    "X-Razorpay-Signature": sig,
                },
            )
            assert response.status_code == 202, response.text

    # Execute the failsafe processing directly
    from app.dispute.routes import process_dispute_and_broadcast
    from app.dispute.schemas.webhook import DisputeWebhookEvent

    event = DisputeWebhookEvent.model_validate(webhook_payload)
    mock_graph = MagicMock()
    await process_dispute_and_broadcast(event, dispute_id, mock_graph)

    # Verify dispute state in PostgreSQL
    async with async_session_factory() as session:
        dispute = (await session.execute(
            select(Dispute).where(Dispute.id == dispute_id)
        )).scalar_one_or_none()

        assert dispute is not None
        assert dispute.status == "awaiting_review"
        assert dispute.outcome == "manual_review"

        ctx = dispute.review_context
        assert ctx is not None
        assert ctx.get("gate_action") == "manual_review"
        assert ctx.get("unmatched_records_failsafe") is True
        assert ctx.get("winnability_score") == 0.0
        assert ctx.get("customer_legitimacy_signal") is False
        assert "missing_order_record" in ctx.get("risk_factors", [])
        assert "Neither order_id" in ctx.get("triage_reasoning", "")
        assert "This system cannot solve this dispute" in ctx.get("human_review_reason", "")

    # Now verify that manual review endpoint handles the bypassed failsafe dispute
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        review_resp = await client.post(
            f"/api/v1/disputes/{dispute_id}/review",
            json={
                "action": "reject",
                "reason": "Merchant records unverified in DB. Accepting loss manually.",
            },
        )
        assert review_resp.status_code == 202, f"{review_resp.status_code}: {review_resp.text}"
        review_data = review_resp.json()
        assert review_data["status"] == "resolved"
        assert review_data["action"] == "reject"

    # Verify final resolved state in DB
    async with async_session_factory() as session:
        dispute = (await session.execute(
            select(Dispute).where(Dispute.id == dispute_id)
        )).scalar_one_or_none()
        assert dispute is not None
        assert dispute.status == "resolved"
        assert dispute.outcome == "accept_loss"
        assert dispute.review_context.get("reviewer_decision") == "reject"
