"""
Defense-only repository for evidence retrieval.

CRITICAL CONSTRAINT: This repository provides READ-ONLY access to the
merchant database. No INSERT, UPDATE, or DELETE operations are exposed.
The agent can only gather evidence — never mutate merchant data.
"""

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.dispute.models import (
    CustomerCommunication,
    Order,
    RiskSignal,
    ShippingLog,
)


class EvidenceRepository:
    """
    Async repository for fetching dispute evidence from the merchant DB.
    All methods are read-only SELECT queries.
    """

    def __init__(self, session: AsyncSession):
        self._session = session

    # ── Fetch by Order ID ──

    async def get_order_by_id(self, order_id: str) -> Optional[Order]:
        """Fetch a single order with all related evidence eagerly loaded."""
        stmt = (
            select(Order)
            .where(Order.order_id == order_id)
            .options(
                selectinload(Order.shipping_logs),
                selectinload(Order.communications),
                selectinload(Order.risk_signals),
            )
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    # ── Fetch by Payment ID ──

    async def get_order_by_payment_id(self, payment_id: str) -> Optional[Order]:
        """Fetch a single order via its Razorpay payment ID."""
        stmt = (
            select(Order)
            .where(Order.payment_id == payment_id)
            .options(
                selectinload(Order.shipping_logs),
                selectinload(Order.communications),
                selectinload(Order.risk_signals),
            )
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    # ── Fetch individual evidence tables ──

    async def get_shipping_logs(self, order_id: str) -> list[ShippingLog]:
        """Fetch all shipping/delivery records for an order."""
        stmt = select(ShippingLog).where(ShippingLog.order_id == order_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_communications(self, order_id: str) -> list[CustomerCommunication]:
        """Fetch all customer interaction transcripts for an order."""
        stmt = select(CustomerCommunication).where(
            CustomerCommunication.order_id == order_id
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_risk_signals(self, order_id: str) -> list[RiskSignal]:
        """Fetch all authentication/telemetry signals for an order."""
        stmt = select(RiskSignal).where(RiskSignal.order_id == order_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    # ── Convenience: Full evidence bundle ──

    async def fetch_full_evidence(
        self,
        order_id: Optional[str] = None,
        payment_id: Optional[str] = None,
    ) -> Optional[dict]:
        """
        Fetch the complete evidence bundle for a dispute.
        Accepts either order_id or payment_id (at least one required).

        Returns a dict matching the fetch_dispute_evidence tool schema,
        or None if the order is not found.
        """
        if not order_id and not payment_id:
            raise ValueError("At least one of order_id or payment_id must be provided")

        # Resolve order
        if order_id:
            order = await self.get_order_by_id(order_id)
        else:
            order = await self.get_order_by_payment_id(payment_id)

        if order is None:
            return None

        # Serialize to dict matching agentToolDefinition.txt return schema
        shipping = order.shipping_logs[0] if order.shipping_logs else None
        risk = order.risk_signals[0] if order.risk_signals else None

        return {
            "order": {
                "order_id": order.order_id,
                "payment_id": order.payment_id,
                "customer_email": order.customer_email,
                "amount_inr": order.amount_inr,
                "item_description": order.item_description,
                "created_at": order.created_at.isoformat() if order.created_at else None,
            },
            "shipping": {
                "tracking_id": shipping.tracking_id,
                "courier_partner": shipping.courier_partner,
                "delivery_status": shipping.delivery_status,
                "signed_by": shipping.signed_by,
                "delivery_timestamp": (
                    shipping.delivery_timestamp.isoformat()
                    if shipping.delivery_timestamp
                    else None
                ),
            } if shipping else None,
            "communications": [
                {
                    "ticket_id": comm.ticket_id,
                    "channel": comm.channel,
                    "message_transcript": comm.message_transcript,
                    "logged_at": comm.logged_at.isoformat() if comm.logged_at else None,
                }
                for comm in order.communications
            ],
            "risk_signals": {
                "ip_address": risk.ip_address,
                "device_fingerprint": risk.device_fingerprint,
                "is_2fa_verified": risk.is_2fa_verified,
                "account_age_days": risk.account_age_days,
            } if risk else None,
        }
