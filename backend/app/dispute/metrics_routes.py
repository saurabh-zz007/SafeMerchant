"""
REST endpoints for metrics, breakdowns, audit history, and dispute edits.

Endpoints:
  GET   /metrics/summary          — daily aggregated totals for a date range
  GET   /metrics/breakdown        — current breakdown by dimension
  GET   /metrics/repeat-patterns  — repeat customer/email patterns
  PATCH /disputes/{id}            — human edit (with transactional audit log)
  GET   /disputes/{id}/audit      — audit trail for one dispute
"""

from __future__ import annotations

import logging
from datetime import date, datetime

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, status

from app.core.db import async_session_factory
from app.dispute.dispute_repository import DisputeRepository
from app.dispute.metrics_repository import MetricsRepository
from app.dispute.schemas.metrics import (
    AuditHistoryResponse,
    AuditLogEntry,
    BreakdownItem,
    BreakdownResponse,
    DailySummaryRow,
    DisputePatchRequest,
    MetricsSummaryResponse,
    MetricsSummaryTotals,
    RepeatPatternItem,
    RepeatPatternsResponse,
)
from app.dispute import metrics_service

logger = logging.getLogger(__name__)
router = APIRouter()

# Valid dimensions for breakdown queries
VALID_BREAKDOWN_DIMENSIONS = {"reason_code", "outcome", "phase"}


# ── Metrics Summary ─────────────────────────────────────────────────


@router.get(
    "/metrics/summary",
    tags=["metrics"],
    summary="Aggregated daily metrics for a date range",
    response_model=MetricsSummaryResponse,
)
async def get_metrics_summary(
    from_date: date = Query(
        ..., alias="from", description="Start date (inclusive), ISO format"
    ),
    to_date: date = Query(
        ..., alias="to", description="End date (inclusive), ISO format"
    ),
):
    """Returns aggregated totals from ``dispute_metrics_daily``.

    Never scans ``disputes`` or ``dispute_events`` directly.
    """
    if from_date > to_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="'from' date must be <= 'to' date",
        )

    async with async_session_factory() as session:
        repo = MetricsRepository(session)
        rows = await repo.get_daily_summary(from_date, to_date)

    # Compute totals across the range
    total_disputes = sum(r.total_disputes for r in rows)
    won = sum(r.won for r in rows)
    lost = sum(r.lost for r in rows)
    action_required = sum(r.action_required for r in rows)
    amount_won = sum(r.amount_won_paise for r in rows)
    amount_lost = sum(r.amount_lost_paise for r in rows)
    amount_at_risk = sum(r.amount_at_risk_paise for r in rows)
    sla_breached = sum(r.sla_breached for r in rows)

    resolved = won + lost
    win_rate = (won / resolved) if resolved > 0 else None

    return MetricsSummaryResponse(
        from_date=from_date,
        to_date=to_date,
        totals=MetricsSummaryTotals(
            total_disputes=total_disputes,
            won=won,
            lost=lost,
            action_required=action_required,
            amount_won_paise=amount_won,
            amount_lost_paise=amount_lost,
            amount_at_risk_paise=amount_at_risk,
            sla_breached=sla_breached,
            win_rate=round(win_rate, 4) if win_rate is not None else None,
        ),
        daily=[DailySummaryRow.model_validate(r) for r in rows],
    )


# ── Breakdowns ───────────────────────────────────────────────────────


@router.get(
    "/metrics/breakdown",
    tags=["metrics"],
    summary="Current breakdown by dimension",
    response_model=BreakdownResponse,
)
async def get_metrics_breakdown(
    by: str = Query(
        ..., description="Dimension to break down by: reason_code | outcome | phase"
    ),
):
    """Returns current counts from ``dispute_breakdowns`` (pre-computed).

    Never scans ``disputes`` directly.
    """
    if by not in VALID_BREAKDOWN_DIMENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid dimension '{by}'. Must be one of: {', '.join(sorted(VALID_BREAKDOWN_DIMENSIONS))}",
        )

    async with async_session_factory() as session:
        repo = MetricsRepository(session)
        items = await repo.get_breakdown(by)
        refreshed_at = await repo.get_breakdown_refreshed_at()

    return BreakdownResponse(
        by=by,
        items=[BreakdownItem.model_validate(i) for i in items],
        refreshed_at=refreshed_at,
    )


# ── Repeat Patterns ──────────────────────────────────────────────────


@router.get(
    "/metrics/repeat-patterns",
    tags=["metrics"],
    summary="Repeat customer/email patterns across disputes",
    response_model=RepeatPatternsResponse,
)
async def get_repeat_patterns(
    min_count: int = Query(
        default=2, ge=2, description="Minimum dispute count to flag as repeat"
    ),
):
    """Find customer emails appearing across multiple disputes."""
    async with async_session_factory() as session:
        repo = MetricsRepository(session)
        patterns = await repo.get_repeat_patterns(min_count)

    return RepeatPatternsResponse(
        patterns=[RepeatPatternItem(**p) for p in patterns],
    )


# ── Dispute PATCH (Human Edit) ───────────────────────────────────────


@router.patch(
    "/disputes/{dispute_id}",
    tags=["disputes"],
    summary="Edit dispute fields (human correction)",
    status_code=status.HTTP_200_OK,
)
async def patch_dispute(
    dispute_id: str,
    patch: DisputePatchRequest,
    background_tasks: BackgroundTasks,
):
    """Edit a dispute's mutable fields.

    This endpoint:
      1. Updates the ``disputes`` row
      2. Writes one ``dispute_audit_log`` row per changed field
      3. Both in a **single transaction**
      4. After commit, broadcasts a ``metrics_stale`` signal
    """
    # Build changes dict from non-None fields (excluding 'note')
    changes = {}
    if patch.status is not None:
        changes["status"] = patch.status
    if patch.amount_paise is not None:
        changes["amount_paise"] = patch.amount_paise
    if patch.reason_code is not None:
        changes["reason_code"] = patch.reason_code
    if patch.outcome is not None:
        changes["outcome"] = patch.outcome

    if not changes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No editable fields provided",
        )

    async with async_session_factory() as session:
        repo = DisputeRepository(session)

        try:
            audit_entries = await repo.update_dispute_fields(
                dispute_id=dispute_id,
                changes=changes,
                changed_by="user",
                note=patch.note,
            )
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(e),
            )

    if not audit_entries:
        return {
            "dispute_id": dispute_id,
            "message": "No fields were changed (values already match)",
            "changes": 0,
        }

    # Trigger background metrics refresh + websocket signal
    background_tasks.add_task(metrics_service.on_dispute_edited, dispute_id)

    return {
        "dispute_id": dispute_id,
        "message": f"{len(audit_entries)} field(s) updated",
        "changes": len(audit_entries),
        "fields": [e.field for e in audit_entries],
    }


# ── Audit History ────────────────────────────────────────────────────


@router.get(
    "/disputes/{dispute_id}/audit",
    tags=["disputes"],
    summary="Audit trail for a single dispute",
    response_model=AuditHistoryResponse,
)
async def get_dispute_audit(dispute_id: str):
    """Returns the complete audit history for one dispute."""
    async with async_session_factory() as session:
        # Verify dispute exists
        dispute_repo = DisputeRepository(session)
        dispute = await dispute_repo.get_dispute(dispute_id)

        if dispute is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Dispute {dispute_id} not found",
            )

        metrics_repo = MetricsRepository(session)
        entries = await metrics_repo.get_audit_history(dispute_id)

    return AuditHistoryResponse(
        dispute_id=dispute_id,
        entries=[AuditLogEntry.model_validate(e) for e in entries],
    )
