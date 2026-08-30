"""
Metrics background service.

Orchestrates incremental and full metric updates, breakdown refreshes,
and websocket invalidation signals.  All heavy work runs as a
``BackgroundTasks`` callable — never in the request path.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Optional

from app.core.db import async_session_factory
from app.dispute.metrics_repository import MetricsRepository
from app.dispute.websocket import manager

logger = logging.getLogger(__name__)


async def on_dispute_ingested(
    dispute_id: str,
    webhook_payload: dict,
    amount_paise: Optional[int] = None,
) -> None:
    """Called (as a background task) after a webhook writes to dispute_events + disputes.

    Performs:
      1. Incremental daily metrics update for today (+1 total, + amount at risk)
      2. Breakdown refresh
      3. metrics_stale websocket signal
    """
    today = date.today()

    async with async_session_factory() as session:
        repo = MetricsRepository(session)

        await repo.increment_daily_metrics(
            today,
            total_disputes_delta=1,
            amount_at_risk_paise_delta=amount_paise or 0,
        )

        await repo.refresh_breakdowns()

    await manager.broadcast_metrics_stale("all")
    logger.info("Metrics updated after ingestion of dispute %s", dispute_id)


async def on_dispute_resolved(
    dispute_id: str,
    outcome: str,
    amount_paise: int = 0,
    response_seconds: Optional[int] = None,
) -> None:
    """Called (as a background task) when a dispute reaches a terminal state.

    Performs:
      1. Incremental daily metrics update (move from at-risk to won/lost)
      2. Breakdown refresh
      3. metrics_stale websocket signal
    """
    today = date.today()

    async with async_session_factory() as session:
        repo = MetricsRepository(session)

        won_delta = 1 if outcome == "won" else 0
        lost_delta = 1 if outcome in ("lost", "accepted_loss") else 0

        await repo.increment_daily_metrics(
            today,
            won_delta=won_delta,
            lost_delta=lost_delta,
            amount_won_paise_delta=amount_paise if outcome == "won" else 0,
            amount_lost_paise_delta=amount_paise if outcome in ("lost", "accepted_loss") else 0,
            # Remove from at-risk since it's now resolved
            amount_at_risk_paise_delta=-amount_paise if amount_paise else 0,
        )

        await repo.refresh_breakdowns()

    await manager.broadcast_metrics_stale("all")
    logger.info(
        "Metrics updated after resolution of dispute %s (outcome=%s)",
        dispute_id, outcome,
    )


async def on_dispute_edited(dispute_id: str) -> None:
    """Called (as a background task) after a human PATCH edit.

    Performs:
      1. Breakdown refresh (the edit may have changed reason_code / outcome)
      2. metrics_stale websocket signal

    Note: We don't recompute daily metrics here because a single field edit
    rarely changes the daily aggregate.  If the outcome was changed, the
    full daily recomputation can be triggered separately.
    """
    async with async_session_factory() as session:
        repo = MetricsRepository(session)
        await repo.refresh_breakdowns()

    await manager.broadcast_metrics_stale("all")
    logger.info("Metrics refreshed after edit of dispute %s", dispute_id)


async def refresh_breakdowns_background() -> None:
    """Standalone background task to refresh breakdowns."""
    async with async_session_factory() as session:
        repo = MetricsRepository(session)
        await repo.refresh_breakdowns()

    await manager.broadcast_metrics_stale("breakdown")
    logger.info("Breakdown refresh completed (background)")


async def recompute_daily_metrics_background(target_date: date) -> None:
    """Standalone background task to fully recompute a day's metrics."""
    async with async_session_factory() as session:
        repo = MetricsRepository(session)
        await repo.recompute_daily_metrics(target_date)

    await manager.broadcast_metrics_stale("daily_summary")
    logger.info("Daily metrics recomputed for %s (background)", target_date)
