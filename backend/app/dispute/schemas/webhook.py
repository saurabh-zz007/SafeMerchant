"""
Pydantic models for the Razorpay payment.dispute.created webhook payload.

These schemas validate incoming webhook JSON before it enters the LangGraph.
Built to match Razorpay's actual nested dispute webhook structure.
"""

from typing import Any, List, Optional, Union
from pydantic import BaseModel, Field


class PaymentEntity(BaseModel):
    """The original payment object inside the webhook payload (lean model)."""
    id: str = Field(..., description="Razorpay payment ID (e.g., pay_XYZ1001)")
    entity: str = Field(default="payment")
    amount: int = Field(..., description="Original payment amount in paise")
    currency: str = Field(default="INR")
    status: str = Field(default="captured", description="Payment status (e.g., captured)")
    order_id: Optional[str] = Field(default=None, description="Merchant order ID (e.g., ORD_1001)")
    email: Optional[str] = Field(default=None, description="Customer email")
    contact: Optional[str] = Field(default=None, description="Customer contact phone")
    method: Optional[str] = Field(default=None, description="Payment method (e.g., card, upi)")
    amount_refunded: Optional[int] = Field(default=0)
    refund_status: Optional[str] = None
    captured: Optional[bool] = None
    created_at: Optional[int] = None

    model_config = {"extra": "ignore"}


class PaymentWrapper(BaseModel):
    entity: PaymentEntity

    model_config = {"extra": "ignore"}


class DisputeEvidenceEntity(BaseModel):
    """
    Evidence fields in dispute.entity.evidence matching Razorpay's exact specification.
    """
    amount: Optional[int] = Field(default=None, description="Evidence / contest amount in paise")
    summary: Optional[str] = Field(default=None, description="Summary of evidence")
    shipping_proof: Optional[Union[List[str], str]] = Field(default=None, description="Shipping/delivery proof doc IDs")
    billing_proof: Optional[Union[List[str], str]] = Field(default=None, description="Billing proof doc IDs")
    cancellation_proof: Optional[Union[List[str], str]] = Field(default=None, description="Cancellation proof doc IDs")
    customer_communication: Optional[Union[List[str], str]] = Field(default=None, description="Customer communication transcript doc IDs")
    proof_of_service: Optional[Union[List[str], str]] = Field(default=None, description="Proof of service doc IDs")
    explanation_letter: Optional[Union[List[str], str]] = Field(default=None, description="Explanation letter doc IDs")
    refund_confirmation: Optional[Union[List[str], str]] = Field(default=None, description="Refund confirmation doc IDs")
    access_activity_log: Optional[Union[List[str], str]] = Field(default=None, description="Access activity log doc IDs")
    refund_cancellation_policy: Optional[Union[List[str], str]] = Field(default=None, description="Refund & cancellation policy doc IDs")
    term_and_conditions: Optional[Union[List[str], str]] = Field(default=None, description="Terms & conditions doc IDs")
    others: Optional[Union[List[str], str]] = Field(default=None, description="Other supporting document doc IDs")
    submitted_at: Optional[int] = Field(default=None, description="Unix timestamp of evidence submission")

    model_config = {"extra": "ignore"}


class DisputeEntity(BaseModel):
    """The dispute object inside the webhook payload."""
    id: str = Field(..., description="Razorpay dispute ID (e.g., disp_XXXX)")
    entity: str = Field(default="dispute")
    payment_id: str = Field(..., description="Razorpay payment ID")
    amount: int = Field(..., description="Disputed amount in paise")
    currency: str = Field(default="INR")
    amount_deducted: Optional[int] = Field(default=0, description="Amount deducted by Razorpay in paise")
    reason_code: str = Field(
        ...,
        description="Dispute reason code (e.g., chargeback, fraud, processed_invalid_expired_card, etc.)",
    )
    respond_by: Optional[int] = Field(
        default=None, description="Unix timestamp deadline to respond to dispute"
    )
    status: str = Field(default="open")
    evidence: Optional[DisputeEvidenceEntity] = Field(
        default=None, description="Evidence object matching Razorpay structure"
    )
    phase: str = Field(
        default="chargeback",
        description="Dispute phase: chargeback | pre_arbitration | arbitration",
    )
    created_at: Optional[int] = Field(
        default=None, description="Unix timestamp of dispute creation"
    )

    model_config = {"extra": "ignore"}


class DisputeWrapper(BaseModel):
    entity: DisputeEntity

    model_config = {"extra": "ignore"}


class DisputePayload(BaseModel):
    """The inner payload containing BOTH the payment and dispute entities."""
    payment: PaymentWrapper
    dispute: DisputeWrapper

    model_config = {"extra": "ignore"}


class DisputeWebhookEvent(BaseModel):
    """
    Top-level webhook event from Razorpay.
    """
    entity: Optional[str] = Field(default="event")
    account_id: Optional[str] = Field(
        default=None, description="Razorpay merchant account ID"
    )
    event: str = Field(
        ...,
        description="Webhook event type (e.g., payment.dispute.created)",
    )
    contains: List[str] = Field(
        default_factory=lambda: ["payment", "dispute"],
        description="List of entities contained in the payload (e.g., ['payment', 'dispute'])"
    )
    payload: DisputePayload
    created_at: Optional[int] = Field(
        default=None, description="Unix timestamp of event creation"
    )

    model_config = {"extra": "ignore"}
