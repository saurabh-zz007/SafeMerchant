"""
Pydantic models for the Razorpay payment.dispute.created webhook payload.

These schemas validate incoming webhook JSON before it enters the LangGraph.
Built to match Razorpay's actual nested dispute webhook structure.
"""

from typing import Optional, List
from pydantic import BaseModel, Field


class PaymentEntity(BaseModel):
    """The original payment object inside the webhook payload."""
    id: str = Field(..., description="Razorpay payment ID (e.g., pay_XYZ1001)")
    amount: int = Field(..., description="Original payment amount in paisa")
    currency: str = Field(default="INR")
    status: str = Field(..., description="Payment status (e.g., captured)")
    order_id: str = Field(..., description="Merchant order ID (e.g., ORD_1001)")
    email: str = Field(..., description="Customer email")

class PaymentWrapper(BaseModel):
    entity: PaymentEntity


class DisputeEntity(BaseModel):
    """The dispute object inside the webhook payload."""
    id: str = Field(..., description="Razorpay dispute ID (e.g., disp_XXXX)")
    payment_id: str = Field(..., description="Razorpay payment ID")
    amount: int = Field(..., description="Disputed amount in paisa")
    currency: str = Field(default="INR")
    reason_code: str = Field(
        ...,
        description="Dispute reason: chargeback | fraud | item_not_received | etc.",
    )
    phase: str = Field(
        default="chargeback",
        description="Dispute phase: chargeback | pre_arbitration | fraud",
    )
    status: str = Field(default="open")
    created_at: Optional[int] = Field(
        default=None, description="Unix timestamp of dispute creation"
    )

class DisputeWrapper(BaseModel):
    entity: DisputeEntity


class DisputePayload(BaseModel):
    """The inner payload containing BOTH the payment and dispute entities."""
    payment: PaymentWrapper
    dispute: DisputeWrapper


class DisputeWebhookEvent(BaseModel):
    """
    Top-level webhook event from Razorpay.
    """
    event: str = Field(
        ...,
        description="Webhook event type (e.g., payment.dispute.created)",
    )
    contains: List[str] = Field(
        default_factory=list,
        description="List of entities contained in the payload (e.g., ['payment', 'dispute'])"
    )
    payload: DisputePayload
    account_id: Optional[str] = Field(
        default=None, description="Razorpay merchant account ID"
    )
