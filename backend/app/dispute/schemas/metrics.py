"""
Pydantic models for metrics, audit, and dispute-edit endpoints.

Covers:
  - GET /metrics/summary        → MetricsSummaryResponse
  - GET /metrics/breakdown      → BreakdownResponse
  - GET /metrics/repeat-patterns → RepeatPatternsResponse
  - PATCH /disputes/{id}        → DisputePatchRequest
  - GET /disputes/{id}/audit    → AuditHistoryResponse
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field


# ── Daily Summary ────────────────────────────────────────────────────

class DailySummaryRow(BaseModel):
    """One row from ``dispute_metrics_daily``."""

    date: date
    total_disputes: int = 0
    won: int = 0
    lost: int = 0
    action_required: int = 0
    amount_won_paise: int = 0
    amount_lost_paise: int = 0
    amount_at_risk_paise: int = 0
    avg_response_seconds: Optional[int] = None
    sla_breached: int = 0

    model_config = {"from_attributes": True}


class MetricsSummaryTotals(BaseModel):
    """Aggregated totals across the requested date range."""

    total_disputes: int = 0
    won: int = 0
    lost: int = 0
    action_required: int = 0
    amount_won_paise: int = 0
    amount_lost_paise: int = 0
    amount_at_risk_paise: int = 0
    sla_breached: int = 0
    win_rate: Optional[float] = Field(
        None, description="Won / (Won + Lost), null if no resolved disputes"
    )


class MetricsSummaryResponse(BaseModel):
    """Response for ``GET /metrics/summary``."""

    from_date: date
    to_date: date
    totals: MetricsSummaryTotals
    daily: list[DailySummaryRow]


# ── Breakdowns ───────────────────────────────────────────────────────

class BreakdownItem(BaseModel):
    """One row from ``dispute_breakdowns``."""

    dimension: str
    dimension_value: str
    count: int = 0
    amount_paise: int = 0

    model_config = {"from_attributes": True}


class BreakdownResponse(BaseModel):
    """Response for ``GET /metrics/breakdown``."""

    by: str
    items: list[BreakdownItem]
    refreshed_at: Optional[datetime] = None


# ── Repeat Patterns ──────────────────────────────────────────────────

class RepeatPatternItem(BaseModel):
    """A customer email that appears across multiple disputes."""

    customer_email: str
    dispute_count: int
    total_amount_paise: int
    dispute_ids: list[str]


class RepeatPatternsResponse(BaseModel):
    """Response for ``GET /metrics/repeat-patterns``."""

    patterns: list[RepeatPatternItem]


# ── Audit Log ────────────────────────────────────────────────────────

class AuditLogEntry(BaseModel):
    """One row from ``dispute_audit_log``."""

    id: int
    dispute_id: str
    field: str
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    changed_by: str
    changed_at: datetime
    note: Optional[str] = None

    model_config = {"from_attributes": True}


class AuditHistoryResponse(BaseModel):
    """Response for ``GET /disputes/{id}/audit``."""

    dispute_id: str
    entries: list[AuditLogEntry]


# ── Dispute Patch (Human Edit) ───────────────────────────────────────

class DisputePatchRequest(BaseModel):
    """
    Request body for ``PATCH /disputes/{id}``.

    Only provided fields will be updated.  Every changed field produces
    a row in ``dispute_audit_log`` within the same transaction.
    """

    status: Optional[str] = Field(
        None, description="New status value"
    )
    amount_paise: Optional[int] = Field(
        None, description="Corrected disputed amount in paise"
    )
    reason_code: Optional[str] = Field(
        None, description="Corrected reason code"
    )
    outcome: Optional[str] = Field(
        None, description="Corrected outcome (won / lost / open / accepted_loss)"
    )
    note: Optional[str] = Field(
        None, description="Free-text note explaining the edit"
    )
