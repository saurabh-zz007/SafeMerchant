"""
Pydantic models for the HITL review endpoint and dispute listing.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class ReviewDecision(BaseModel):
    """
    Payload for ``POST /api/v1/disputes/{dispute_id}/review``.

    Actions:
      - ``accept``: Approve and proceed with the graph flow (submit the
        dispute response / approve the refund).
      - ``reject``: Reject the recommendation and accept the loss.
    """

    action: str = Field(
        ...,
        pattern=r"^(accept|reject)$",
        description="'accept' to proceed with the graph or 'reject' to accept the loss",
    )
    reason: str = Field(
        default="",
        description="Optional free-text reason for the decision",
    )


class DisputeListItem(BaseModel):
    """Response model for a single dispute in the list endpoint."""

    id: str
    status: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    history: list[dict[str, Any]] = Field(default_factory=list)

    amount_paise: Optional[int] = None
    reason_code: Optional[str] = None
    customer_email: Optional[str] = None
    payment_id: Optional[str] = None
    order_id: Optional[str] = None
    phase: Optional[str] = None
    outcome: Optional[str] = None
    updated_by: Optional[str] = None
    resolved_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
