"""
Metrics background service.

Orchestrates incremental daily metric updates, periodic breakdown refreshes,
and websocket invalidation signals.
"""

from __future__ import annotations

import asyncio
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
    """Called (as a background task) ONLY when a genuinely NEW dispute is ingested.

    Performs:
      1. Records append-only event in dispute_events
      2. Incremental atomic daily metrics update for today (+1 total, + amount at risk)
      3. metrics_stale websocket signal
    """
    today = date.today()

    async with async_session_factory() as session:
        repo = MetricsRepository(session)

        try:
            await repo.record_event(
                dispute_id=dispute_id,
                event_type="webhook_received",
                payload=webhook_payload,
            )
        except Exception as exc:
            logger.warning("Failed to record webhook_received event for dispute %s: %s", dispute_id, exc)

        await repo.increment_daily_metrics(
            today,
            total_disputes_delta=1,
            amount_at_risk_paise_delta=amount_paise or 0,
        )

    await manager.broadcast_metrics_stale("daily_summary")
    logger.info("Daily metrics incremented and event recorded after ingestion of new dispute %s", dispute_id)


async def on_dispute_resolved(
    dispute_id: str,
    outcome: str,
    amount_paise: int = 0,
    response_seconds: Optional[int] = None,
) -> None:
    """Called (as a background task) when a dispute reaches a terminal state.

    Performs:
      1. Incremental atomic daily metrics update (move from at-risk to won/lost)
      2. metrics_stale websocket signal
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

    await manager.broadcast_metrics_stale("daily_summary")
    logger.info(
        "Daily metrics updated after resolution of dispute %s (outcome=%s)",
        dispute_id, outcome,
    )


async def on_dispute_edited(dispute_id: str) -> None:
    """Called (as a background task) after a human PATCH edit.

    Broadcasts metrics stale signal to dashboard clients.
    """
    await manager.broadcast_metrics_stale("all")
    logger.info("Metrics stale broadcast after edit of dispute %s", dispute_id)


async def refresh_breakdowns_background() -> None:
    """Standalone task to refresh dispute_breakdowns table."""
    async with async_session_factory() as session:
        repo = MetricsRepository(session)
        await repo.refresh_breakdowns()

    await manager.broadcast_metrics_stale("breakdown")
    logger.info("Breakdown table refresh completed")


async def recompute_daily_metrics_background(target_date: date) -> None:
    """Standalone background task to fully recompute a day's metrics."""
    async with async_session_factory() as session:
        repo = MetricsRepository(session)
        await repo.recompute_daily_metrics(target_date)

    await manager.broadcast_metrics_stale("daily_summary")
    logger.info("Daily metrics recomputed for %s (background)", target_date)


class PeriodicBreakdownWorker:
    """
    Background worker that periodically refreshes the dispute_breakdowns
    aggregate table (every 30-60s) independent of individual webhook requests.
    Eliminates database lock contention on concurrent webhook ingestion.
    """

    def __init__(self, interval_seconds: float = 30.0) -> None:
        self.interval_seconds = interval_seconds
        self._running: bool = False
        self._task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop(), name="periodic-breakdown-worker")
        logger.info("🚀 PeriodicBreakdownWorker started (interval=%.0fs)", self.interval_seconds)

    async def stop(self) -> None:
        if not self._running:
            return
        logger.info("🛑 Stopping PeriodicBreakdownWorker...")
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("✅ PeriodicBreakdownWorker stopped.")

    async def _run_loop(self) -> None:
        # Initial refresh on startup after 2s grace
        await asyncio.sleep(2.0)
        try:
            await refresh_breakdowns_background()
        except Exception as exc:
            logger.warning("Initial breakdown refresh on startup failed: %s", exc)

        while self._running:
            try:
                await asyncio.sleep(self.interval_seconds)
                if not self._running:
                    break
                await refresh_breakdowns_background()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.exception("Error during periodic breakdown refresh: %s", exc)


# Global singleton instance
breakdown_worker = PeriodicBreakdownWorker(interval_seconds=30.0)
