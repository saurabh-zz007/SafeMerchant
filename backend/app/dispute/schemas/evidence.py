"""
Pydantic models for the evidence bundle returned by the repository.

These mirror the return schema of the fetch_dispute_evidence tool
defined in agentToolDefinition.txt, but as validated Pydantic models
for API responses and serialization.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class OrderEvidence(BaseModel):
    """Order details from the merchant ledger."""

    order_id: str
    payment_id: str
    customer_email: str
    amount_inr: int
    item_description: str
    created_at: Optional[str] = None


class ShippingEvidence(BaseModel):
    """Physical logistics & delivery proof."""

    tracking_id: str
    courier_partner: str
    delivery_status: str
    signed_by: Optional[str] = None
    delivery_timestamp: Optional[str] = None


class CommunicationEvidence(BaseModel):
    """Customer interaction transcript."""

    ticket_id: str
    channel: str
    message_transcript: str
    logged_at: Optional[str] = None


class RiskSignalEvidence(BaseModel):
    """Authentication & network telemetry."""

    ip_address: str
    device_fingerprint: str
    is_2fa_verified: bool
    account_age_days: int


class FullEvidenceBundle(BaseModel):
    """
    Complete evidence package for a dispute.
    Matches the return value of EvidenceRepository.fetch_full_evidence().
    """

    order: OrderEvidence
    shipping: Optional[ShippingEvidence] = None
    communications: list[CommunicationEvidence] = Field(default_factory=list)
    risk_signals: Optional[RiskSignalEvidence] = None


class DisputeResult(BaseModel):
    """API response model for a processed dispute."""

    dispute_id: str
    order_id: str
    payment_id: str
    winnability_score: Optional[float] = None
    gate_action: Optional[str] = None
    requires_human_review: bool = False
    draft_response_letter: Optional[str] = None
    evidence: Optional[FullEvidenceBundle] = None
    current_node: Optional[str] = None
    error: Optional[str] = None
