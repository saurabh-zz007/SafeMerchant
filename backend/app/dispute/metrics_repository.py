"""
Metrics repository — CRUD operations on metrics, breakdowns, and audit tables.

Handles:
  - dispute_events (append-only writes)
  - dispute_audit_log (append-only writes + reads)
  - dispute_metrics_daily (upsert + range queries)
  - dispute_breakdowns (full-refresh recomputation + reads)
  - Repeat-customer pattern detection
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import delete, func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.dispute.models import (
    Dispute,
    DisputeAuditLog,
    DisputeBreakdown,
    DisputeEvent,
    DisputeMetricsDaily,
)

logger = logging.getLogger(__name__)


class MetricsRepository:
    """Async repository for metrics, audit, and event log operations."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ══════════════════════════════════════════════════════════════
    # DISPUTE EVENTS — append-only
    # ══════════════════════════════════════════════════════════════

    async def record_event(
        self,
        dispute_id: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> DisputeEvent:
        """Insert a row into ``dispute_events`` (append-only, immutable)."""
        event = DisputeEvent(
            dispute_id=dispute_id,
            event_type=event_type,
            payload=payload,
            occurred_at=datetime.now(timezone.utc),
        )
        self._session.add(event)
        await self._session.flush()
        logger.info("Recorded event %s for dispute %s", event_type, dispute_id)
        return event

    # ══════════════════════════════════════════════════════════════
    # AUDIT LOG — append-only writes + reads
    # ══════════════════════════════════════════════════════════════

    async def write_audit_log(
        self,
        dispute_id: str,
        field: str,
        old_value: Optional[str],
        new_value: Optional[str],
        changed_by: str = "user",
        note: Optional[str] = None,
    ) -> DisputeAuditLog:
        """Insert one audit row.  Must be called in the same txn as the update."""
        entry = DisputeAuditLog(
            dispute_id=dispute_id,
            field=field,
            old_value=old_value,
            new_value=new_value,
            changed_by=changed_by,
            changed_at=datetime.now(timezone.utc),
            note=note,
        )
        self._session.add(entry)
        await self._session.flush()
        return entry

    async def get_audit_history(self, dispute_id: str) -> list[DisputeAuditLog]:
        """Fetch all audit log entries for a dispute, ordered chronologically."""
        stmt = (
            select(DisputeAuditLog)
            .where(DisputeAuditLog.dispute_id == dispute_id)
            .order_by(DisputeAuditLog.changed_at.asc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    # ══════════════════════════════════════════════════════════════
    # DAILY METRICS — upsert + range queries
    # ══════════════════════════════════════════════════════════════

    async def increment_daily_metrics(
        self,
        target_date: date,
        *,
        total_disputes_delta: int = 0,
        won_delta: int = 0,
        lost_delta: int = 0,
        action_required_delta: int = 0,
        amount_won_paise_delta: int = 0,
        amount_lost_paise_delta: int = 0,
        amount_at_risk_paise_delta: int = 0,
        sla_breached_delta: int = 0,
    ) -> None:
        """Lightweight incremental update via INSERT ... ON CONFLICT UPDATE.

        Adds deltas to existing values (or inserts a new row with the deltas).
        """
        stmt = pg_insert(DisputeMetricsDaily).values(
            date=target_date,
            total_disputes=total_disputes_delta,
            won=won_delta,
            lost=lost_delta,
            action_required=action_required_delta,
            amount_won_paise=amount_won_paise_delta,
            amount_lost_paise=amount_lost_paise_delta,
            amount_at_risk_paise=amount_at_risk_paise_delta,
            sla_breached=sla_breached_delta,
        ).on_conflict_do_update(
            index_elements=["date"],
            set_={
                "total_disputes": DisputeMetricsDaily.total_disputes + total_disputes_delta,
                "won": DisputeMetricsDaily.won + won_delta,
                "lost": DisputeMetricsDaily.lost + lost_delta,
                "action_required": DisputeMetricsDaily.action_required + action_required_delta,
                "amount_won_paise": DisputeMetricsDaily.amount_won_paise + amount_won_paise_delta,
                "amount_lost_paise": DisputeMetricsDaily.amount_lost_paise + amount_lost_paise_delta,
                "amount_at_risk_paise": DisputeMetricsDaily.amount_at_risk_paise + amount_at_risk_paise_delta,
                "sla_breached": DisputeMetricsDaily.sla_breached + sla_breached_delta,
            },
        )
        await self._session.execute(stmt)
        await self._session.commit()
        logger.debug("Incremented daily metrics for %s", target_date)

    async def get_daily_summary(
        self, from_date: date, to_date: date
    ) -> list[DisputeMetricsDaily]:
        """Query ``dispute_metrics_daily`` for a date range (inclusive)."""
        stmt = (
            select(DisputeMetricsDaily)
            .where(
                DisputeMetricsDaily.date >= from_date,
                DisputeMetricsDaily.date <= to_date,
            )
            .order_by(DisputeMetricsDaily.date.asc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def recompute_daily_metrics(self, target_date: date) -> None:
        """Full recomputation of a single day from the ``disputes`` table.

        Used by background tasks when incremental isn't sufficient
        (e.g. after a manual edit changes a past dispute's outcome).
        """
        day_start = datetime(
            target_date.year, target_date.month, target_date.day,
            tzinfo=timezone.utc,
        )
        day_end = day_start + timedelta(days=1)

        # Aggregate from disputes where webhook_received_at falls on this day
        stmt = select(
            func.count().label("total"),
            func.count().filter(Dispute.outcome == "won").label("won"),
            func.count().filter(Dispute.outcome == "lost").label("lost"),
            func.count().filter(Dispute.status == "awaiting_review").label("action_required"),
            func.coalesce(
                func.sum(Dispute.amount_paise).filter(Dispute.outcome == "won"), 0
            ).label("amount_won"),
            func.coalesce(
                func.sum(Dispute.amount_paise).filter(Dispute.outcome == "lost"), 0
            ).label("amount_lost"),
            func.coalesce(
                func.sum(Dispute.amount_paise).filter(Dispute.outcome == "open"), 0
            ).label("amount_at_risk"),
        ).where(
            Dispute.webhook_received_at >= day_start,
            Dispute.webhook_received_at < day_end,
        )

        result = await self._session.execute(stmt)
        row = result.one()

        upsert_stmt = pg_insert(DisputeMetricsDaily).values(
            date=target_date,
            total_disputes=row.total,
            won=row.won,
            lost=row.lost,
            action_required=row.action_required,
            amount_won_paise=row.amount_won,
            amount_lost_paise=row.amount_lost,
            amount_at_risk_paise=row.amount_at_risk,
        ).on_conflict_do_update(
            index_elements=["date"],
            set_={
                "total_disputes": row.total,
                "won": row.won,
                "lost": row.lost,
                "action_required": row.action_required,
                "amount_won_paise": row.amount_won,
                "amount_lost_paise": row.amount_lost,
                "amount_at_risk_paise": row.amount_at_risk,
            },
        )
        await self._session.execute(upsert_stmt)
        await self._session.commit()
        logger.info("Recomputed daily metrics for %s", target_date)

    # ══════════════════════════════════════════════════════════════
    # BREAKDOWNS — full-refresh + reads
    # ══════════════════════════════════════════════════════════════

    async def refresh_breakdowns(self) -> None:
        """Recompute ``dispute_breakdowns`` from the ``disputes`` table.

        Performs DELETE + INSERT in a single transaction to avoid
        stale partial data.
        """
        now = datetime.now(timezone.utc)

        # Clear existing
        await self._session.execute(delete(DisputeBreakdown))

        # Dimensions to aggregate
        dimensions = {
            "reason_code": Dispute.reason_code,
            "outcome": Dispute.outcome,
            "phase": Dispute.phase,
        }

        for dim_name, dim_col in dimensions.items():
            stmt = select(
                dim_col.label("dim_value"),
                func.count().label("cnt"),
                func.coalesce(func.sum(Dispute.amount_paise), 0).label("amt"),
            ).where(
                dim_col.isnot(None),
            ).group_by(dim_col)

            result = await self._session.execute(stmt)

            for row in result.all():
                self._session.add(DisputeBreakdown(
                    dimension=dim_name,
                    dimension_value=row.dim_value,
                    count=row.cnt,
                    amount_paise=row.amt,
                    refreshed_at=now,
                ))

        await self._session.commit()
        logger.info("Refreshed dispute breakdowns")

    async def get_breakdown(self, dimension: str) -> list[DisputeBreakdown]:
        """Query ``dispute_breakdowns`` for a single dimension."""
        stmt = (
            select(DisputeBreakdown)
            .where(DisputeBreakdown.dimension == dimension)
            .order_by(DisputeBreakdown.count.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_breakdown_refreshed_at(self) -> Optional[datetime]:
        """Return the most recent ``refreshed_at`` from breakdowns."""
        stmt = select(func.max(DisputeBreakdown.refreshed_at))
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    # ══════════════════════════════════════════════════════════════
    # REPEAT PATTERNS
    # ══════════════════════════════════════════════════════════════

    async def get_repeat_patterns(self, min_count: int = 2) -> list[dict]:
        """Find customer emails that appear across multiple disputes.

        Returns a list of dicts with: customer_email, dispute_count,
        total_amount_paise, dispute_ids.
        """
        stmt = (
            select(
                Dispute.customer_email,
                func.count().label("dispute_count"),
                func.coalesce(func.sum(Dispute.amount_paise), 0).label("total_amount_paise"),
                func.array_agg(Dispute.id).label("dispute_ids"),
            )
            .where(Dispute.customer_email.isnot(None))
            .group_by(Dispute.customer_email)
            .having(func.count() >= min_count)
            .order_by(func.count().desc())
        )
        result = await self._session.execute(stmt)

        return [
            {
                "customer_email": row.customer_email,
                "dispute_count": row.dispute_count,
                "total_amount_paise": row.total_amount_paise,
                "dispute_ids": list(row.dispute_ids),
            }
            for row in result.all()
        ]
