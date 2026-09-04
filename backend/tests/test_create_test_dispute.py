"""
Unit and integration tests for the Create Test Dispute feature (Developer Option).
"""

from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core.db import async_session_factory, engine
from app.dispute.models import CustomerCommunication, Dispute, Order, RiskSignal, ShippingLog
from app.main import app

pytestmark = pytest.mark.anyio


@pytest.fixture(autouse=True)
async def dispose_db_pool():
    yield
    await engine.dispose()


@patch("app.dispute.routes.process_dispute_and_broadcast", new_callable=AsyncMock)
@patch("app.dispute.routes._get_graph")
@patch("app.dispute.routes.manager.broadcast_system_event", new_callable=AsyncMock)
async def test_create_test_dispute_endpoint_full_flow(
    mock_broadcast,
    mock_get_graph,
    mock_process_task,
):
    """Verify that POST /api/v1/dev/create-test-dispute creates merchant evidence,
    dispatches the signed webhook, and ingests the dispute into PostgreSQL."""
    mock_get_graph.return_value = MagicMock()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        request_body = {
            "amount_inr": 4999,
            "item_description": "Sony WH-1000XM5 Headphones",
            "delivery_status": "Delivered (Signed)",
            "customer_communication": "Customer confirms receipt",
            "is_2fa_verified": True,
            "account_age_days": 240,
            "reason_code": "product_not_received",
        }

        response = await client.post(
            "/api/v1/dev/create-test-dispute",
            json=request_body,
        )

        assert response.status_code == 201, response.text
        data = response.json()
        assert data["status"] == "success"
        assert "dispute_id" in data
        assert data["dispute_id"].startswith("disp_sim_")
        assert "order_id" in data
        assert data["order_id"].startswith("ORD_SIM_")
        assert "payment_id" in data
        assert data["payment_id"].startswith("pay_sim_")

        dispute_id = data["dispute_id"]
        order_id = data["order_id"]
        payment_id = data["payment_id"]

        # Verify rows inserted in database
        async with async_session_factory() as session:
            # 1. Order
            order = (await session.execute(
                select(Order).where(Order.order_id == order_id)
            )).scalar_one_or_none()
            assert order is not None
            assert order.payment_id == payment_id
            assert order.amount_inr == 4999
            assert order.item_description == "Sony WH-1000XM5 Headphones"

            # 2. Shipping Log
            shipping = (await session.execute(
                select(ShippingLog).where(ShippingLog.order_id == order_id)
            )).scalar_one_or_none()
            assert shipping is not None
            assert shipping.delivery_status == "Delivered"
            assert shipping.signed_by == "Self (OTP Verified)"

            # 3. Customer Communication
            comm = (await session.execute(
                select(CustomerCommunication).where(CustomerCommunication.order_id == order_id)
            )).scalar_one_or_none()
            assert comm is not None
            assert "received" in comm.message_transcript.lower()

            # 4. Risk Signal
            risk = (await session.execute(
                select(RiskSignal).where(RiskSignal.order_id == order_id)
            )).scalar_one_or_none()
            assert risk is not None
            assert risk.is_2fa_verified is True
            assert risk.account_age_days == 240

            # 5. Dispute created via webhook pipeline
            dispute = (await session.execute(
                select(Dispute).where(Dispute.id == dispute_id)
            )).scalar_one_or_none()
            assert dispute is not None
            assert dispute.amount_paise == 499900
            assert dispute.reason_code == "product_not_received"
            assert dispute.order_id == order_id
            assert dispute.payment_id == payment_id


@patch("app.dispute.routes.process_dispute_and_broadcast", new_callable=AsyncMock)
@patch("app.dispute.routes._get_graph")
@patch("app.dispute.routes.manager.broadcast_system_event", new_callable=AsyncMock)
async def test_create_test_dispute_lost_in_transit_no_comm(
    mock_broadcast,
    mock_get_graph,
    mock_process_task,
):
    """Verify scenario with Lost in Transit, No Communication, and No 2FA."""
    mock_get_graph.return_value = MagicMock()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        request_body = {
            "amount_inr": 1299,
            "item_description": "Matte Phone Case",
            "delivery_status": "Lost in Transit",
            "customer_communication": "No communication on file",
            "is_2fa_verified": False,
            "account_age_days": 5,
            "reason_code": "chargeback",
        }

        response = await client.post(
            "/api/v1/dev/create-test-dispute",
            json=request_body,
        )

        assert response.status_code == 201, response.text
        data = response.json()
        order_id = data["order_id"]

        async with async_session_factory() as session:
            # Shipping Log should have Lost_In_Transit
            shipping = (await session.execute(
                select(ShippingLog).where(ShippingLog.order_id == order_id)
            )).scalar_one_or_none()
            assert shipping is not None
            assert shipping.delivery_status == "Lost_In_Transit"
            assert shipping.signed_by is None

            # No communication should have been inserted
            comm = (await session.execute(
                select(CustomerCommunication).where(CustomerCommunication.order_id == order_id)
            )).scalar_one_or_none()
            assert comm is None

            # Risk signal
            risk = (await session.execute(
                select(RiskSignal).where(RiskSignal.order_id == order_id)
            )).scalar_one_or_none()
            assert risk is not None
            assert risk.is_2fa_verified is False
            assert risk.account_age_days == 5
