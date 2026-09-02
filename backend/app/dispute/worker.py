"""
Evidence generation job queue worker pool with concurrency cap.

Picks up queued evidence generation jobs from PostgreSQL using row locking
(FOR UPDATE SKIP LOCKED) and processes them concurrently up to a hard cap
(e.g., max 5 concurrent jobs) using asyncio.Semaphore.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional, Set

from app.core.config import settings
from app.core.db import async_session_factory
from app.dispute.dispute_repository import DisputeRepository
from app.dispute.submission import submit_dispute_evidence, DisputeSubmissionError
from app.dispute.websocket import manager

logger = logging.getLogger(__name__)


class EvidenceWorkerPool:
    """
    Background worker pool managing asynchronous, concurrency-capped
    evidence PDF generation and dual-upload jobs.
    """

    def __init__(self, max_concurrency: Optional[int] = None) -> None:
        self.max_concurrency = max_concurrency or settings.max_concurrent_evidence_jobs
        self._semaphore: asyncio.Semaphore = asyncio.Semaphore(self.max_concurrency)
        self._running: bool = False
        self._loop_task: Optional[asyncio.Task] = None
        self._trigger_event: asyncio.Event = asyncio.Event()
        self._active_tasks: Set[asyncio.Task] = set()

    def notify(self) -> None:
        """Wake up the worker loop immediately when a new job is enqueued."""
        self._trigger_event.set()

    async def start(self) -> None:
        """Start the background queue processor."""
        if self._running:
            return
        self._running = True
        self._loop_task = asyncio.create_task(self._worker_loop(), name="evidence-worker-loop")
        logger.info(
            "🚀 EvidenceWorkerPool background task started and active (max concurrency = %d)",
            self.max_concurrency,
        )

    async def stop(self) -> None:
        """Gracefully stop the worker loop and await pending jobs."""
        if not self._running:
            return
        logger.info("🛑 Stopping EvidenceWorkerPool...")
        self._running = False
        self._trigger_event.set()

        if self._loop_task:
            self._loop_task.cancel()
            try:
                await self._loop_task
            except asyncio.CancelledError:
                pass

        if self._active_tasks:
            logger.info("Waiting for %d active evidence tasks to complete...", len(self._active_tasks))
            await asyncio.gather(*self._active_tasks, return_exceptions=True)

        logger.info("✅ EvidenceWorkerPool stopped.")

    async def _worker_loop(self) -> None:
        """Main polling loop."""
        while self._running:
            try:
                # Reset trigger event
                self._trigger_event.clear()

                # Process available jobs as long as we have concurrency slots
                while self._running:
                    # Check if we have available worker slots
                    if self._semaphore.locked() and self._semaphore._value <= 0:
                        break

                    job_info = await self._claim_next_job()
                    if not job_info:
                        break

                    job_id, dispute_id = job_info
                    # Spawn task bounded by semaphore
                    task = asyncio.create_task(
                        self._process_job_wrapper(job_id, dispute_id),
                        name=f"evidence-job-{job_id}",
                    )
                    self._active_tasks.add(task)
                    task.add_done_callback(self._active_tasks.discard)

                # Wait for next notification or ticker interval (2.0s)
                try:
                    await asyncio.wait_for(self._trigger_event.wait(), timeout=2.0)
                except asyncio.TimeoutError:
                    pass

            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.exception("Unexpected error in evidence worker loop: %s", exc)
                await asyncio.sleep(2.0)

    async def _claim_next_job(self) -> Optional[tuple[int, str]]:
        """
        Atomically claim the next queued job from PostgreSQL.
        Returns (job_id, dispute_id) or None if no queued jobs.
        """
        async with async_session_factory() as session:
            repo = DisputeRepository(session)
            job = await repo.fetch_next_queued_job()
            if not job:
                return None

            job_id = job.id
            dispute_id = job.dispute_id

            # Mark as processing
            await repo.update_job_status(job_id, "processing")
            
            # Log job_picked_up audit/history event
            now_iso = datetime.now(timezone.utc).isoformat()
            await repo.append_history(dispute_id, {
                "event": "job_picked_up",
                "job_id": job_id,
                "picked_up_at": now_iso,
            })
            await session.commit()

            logger.info("Worker claimed EvidenceJob #%d for dispute %s", job_id, dispute_id)

            # Broadcast WebSocket notification
            await manager.broadcast_system_event({
                "event": "job_picked_up",
                "dispute_id": dispute_id,
                "job_id": job_id,
            })

            return (job_id, dispute_id)

    async def _process_job_wrapper(self, job_id: int, dispute_id: str) -> None:
        """Execute the evidence job under concurrency semaphore."""
        async with self._semaphore:
            logger.info("Executing EvidenceJob #%d for dispute %s...", job_id, dispute_id)
            try:
                result = await submit_dispute_evidence(dispute_id)
                outcome = result.get("outcome")
                doc_id = result.get("document_id")
                rzp_response = result.get("razorpay_response")
                logger.info(
                    "EvidenceJob #%d finished for dispute %s (outcome=%s, doc_id=%s)",
                    job_id,
                    dispute_id,
                    outcome,
                    doc_id,
                )

                if outcome == "contest_expected_failure":
                    import json
                    err_msg = (
                        json.dumps(rzp_response)
                        if isinstance(rzp_response, (dict, list))
                        else str(rzp_response)
                    )
                    async with async_session_factory() as session:
                        repo = DisputeRepository(session)
                        await repo.update_job_status(job_id, "contest_expected_failure", error_message=err_msg)
                        await repo.update_status(dispute_id, "resolved", case_resolution="resolved_contested")
                        await session.commit()

                    await manager.broadcast_system_event({
                        "event": "contest_sandbox_limitation",
                        "dispute_id": dispute_id,
                        "job_id": job_id,
                        "document_id": doc_id,
                        "razorpay_response": rzp_response,
                        "error_message": err_msg,
                    })
                else:
                    async with async_session_factory() as session:
                        repo = DisputeRepository(session)
                        await repo.update_job_status(job_id, "completed")
                        await repo.update_status(dispute_id, "under_review", case_resolution="resolved_contested")
                        await session.commit()

                    await manager.broadcast_system_event({
                        "event": "evidence_completed",
                        "dispute_id": dispute_id,
                        "job_id": job_id,
                        "document_id": doc_id,
                    })

            except Exception as exc:
                logger.exception("EvidenceJob #%d failed for dispute %s: %s", job_id, dispute_id, exc)
                try:
                    async with async_session_factory() as session:
                        repo = DisputeRepository(session)
                        await repo.update_job_status(job_id, "failed", error_message=str(exc))
                        await repo.update_status(dispute_id, "error")
                        await repo.append_history(dispute_id, {
                            "event": "evidence_job_failed",
                            "job_id": job_id,
                            "error": str(exc),
                        })
                        await session.commit()

                    await manager.broadcast_system_event({
                        "event": "evidence_job_failed",
                        "dispute_id": dispute_id,
                        "job_id": job_id,
                        "error": str(exc),
                    })
                except Exception as inner_exc:
                    logger.exception("Critical failure updating error state for job #%d: %s", job_id, inner_exc)


# Global singleton instance
evidence_worker = EvidenceWorkerPool()
