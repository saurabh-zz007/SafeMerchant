"""
Pydantic schemas for proof-renderer input data.

These models define the *shape* of data the renderer accepts.
They enforce structure, NOT truthfulness — validation of business
facts happens upstream before data reaches the renderer.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class DeliveryProofData(BaseModel):
    """Data required to render a delivery-confirmation proof PDF."""

    order_id: str
    payment_id: str
    customer_name: str
    customer_email: str
    shipping_address: str
    carrier_name: str
    tracking_number: str
    shipped_at: datetime
    delivered_at: datetime
    delivery_status: str = "Delivered"
    signed_by: Optional[str] = None
    proof_url: Optional[str] = Field(
        None, description="URL to carrier tracking page or screenshot"
    )
    additional_notes: Optional[str] = None


class ChatMessage(BaseModel):
    """A single message in a chat transcript."""

    timestamp: datetime
    sender: str  # e.g. "Customer", "Support Agent"
    message: str


class ChatTranscriptData(BaseModel):
    """Data required to render a chat-transcript proof PDF."""

    order_id: str
    payment_id: str
    customer_name: str
    customer_email: str
    agent_name: str
    conversation_started_at: datetime
    conversation_ended_at: datetime
    messages: list[ChatMessage]
    resolution_summary: Optional[str] = None
    additional_notes: Optional[str] = None


class ActivityLogEntry(BaseModel):
    """A single row in an activity/audit log."""

    timestamp: datetime
    actor: str
    action: str
    details: Optional[str] = None


class ActivityLogData(BaseModel):
    """Data required to render an activity-log proof PDF."""

    order_id: str
    payment_id: str
    customer_name: str
    customer_email: str
    log_title: str = "Order Activity Log"
    entries: list[ActivityLogEntry]
    additional_notes: Optional[str] = None
