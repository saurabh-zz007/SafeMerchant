"""
Dispute lifecycle repository — CRUD operations on the ``disputes`` table.

Unlike ``EvidenceRepository`` (read-only merchant data), this repository
writes to the ``disputes`` table to track status transitions, webhook
payloads, node outcomes, and human review decisions.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.dispute.models import Dispute, DisputeAuditLog, EvidenceJob

logger = logging.getLogger(__name__)

# Fields that a human edit via PATCH is allowed to change
EDITABLE_FIELDS = {"status", "amount_paise", "reason_code", "outcome"}

# Status values that represent a terminal dispute state
TERMINAL_STATUSES = {"resolved", "error"}

# Mapping from case_resolution → outcome
RESOLUTION_TO_OUTCOME = {
    "resolved_contested": "won",
    "resolved_refunded": "lost",
    "resolved_accepted_loss": "accepted_loss",
    "pending_review": "open",
}


class DisputeRepository:
    """Async repository for dispute lifecycle tracking."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── Create ──

    async def create_dispute(
        self,
        dispute_id: str,
        webhook_payload: dict[str, Any],
        *,
        amount_paise: Optional[int] = None,
        reason_code: Optional[str] = None,
        customer_email: Optional[str] = None,
        payment_id: Optional[str] = None,
        order_id: Optional[str] = None,
        phase: Optional[str] = None,
    ) -> Dispute:
        """
        Insert a new dispute record with status ``processing``.

        The raw webhook payload is stored as the first entry in ``history``.
        Uses merge for idempotent re-entrant calls.
        """
        history_entry = {
            "event": "webhook_received",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": webhook_payload,
        }

        dispute = Dispute(
            id=dispute_id,
            status="processing",
            history=[history_entry],
            amount_paise=amount_paise,
            reason_code=reason_code,
            customer_email=customer_email,
            payment_id=payment_id,
            order_id=order_id,
            phase=phase or "chargeback",
            outcome="open",
            updated_by="system",
            webhook_received_at=datetime.now(timezone.utc),
        )

        # Merge handles re-entrant calls (idempotent)
        dispute = await self._session.merge(dispute)
        await self._session.commit()
        await self._session.refresh(dispute)

        logger.info("Created dispute record: %s", dispute_id)
        return dispute

    # ── Read ──

    async def get_dispute(self, dispute_id: str) -> Optional[Dispute]:
        """Fetch a single dispute by ID."""
        stmt = select(Dispute).where(Dispute.id == dispute_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_disputes(self, limit: int = 50) -> list[Dispute]:
        """Fetch the most recent disputes, ordered by created_at DESC."""
        stmt = (
            select(Dispute)
            .order_by(Dispute.created_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    # ── Update ──

    async def update_status(
        self,
        dispute_id: str,
        status: str,
        *,
        case_resolution: Optional[str] = None,
    ) -> None:
        """Update the dispute status and ``updated_at`` timestamp.

        If the status is terminal (resolved / error), also sets
        ``resolved_at`` and maps ``case_resolution`` → ``outcome``.
        """
        values: dict[str, Any] = {
            "status": status,
            "updated_at": datetime.now(timezone.utc),
            "updated_by": "system",
        }

        if status in TERMINAL_STATUSES:
            values["resolved_at"] = datetime.now(timezone.utc)

        if case_resolution:
            values["outcome"] = RESOLUTION_TO_OUTCOME.get(
                case_resolution, "open"
            )

        stmt = (
            update(Dispute)
            .where(Dispute.id == dispute_id)
            .values(**values)
        )
        await self._session.execute(stmt)
        await self._session.commit()
        logger.info("Dispute %s → status=%s", dispute_id, status)

    async def append_history(
        self,
        dispute_id: str,
        entry: dict[str, Any],
    ) -> None:
        """
        Append a new entry to the dispute's JSONB ``history`` array.

        Uses PostgreSQL ``||`` operator for atomic JSONB array concatenation.
        """
        entry_with_ts = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **entry,
        }

        stmt = (
            update(Dispute)
            .where(Dispute.id == dispute_id)
            .values(
                history=Dispute.history.concat([entry_with_ts]),
                updated_at=datetime.now(timezone.utc),
            )
        )
        await self._session.execute(stmt)
        await self._session.commit()

    # ── Transactional Human Edit (with audit log) ──

    async def update_dispute_fields(
        self,
        dispute_id: str,
        changes: dict[str, Any],
        changed_by: str = "user",
        note: Optional[str] = None,
    ) -> list[DisputeAuditLog]:
        """Update mutable fields on a dispute and write audit log entries.

        This method:
          1. Fetches the current dispute row
          2. Computes diffs for each changed field
          3. Updates the ``disputes`` row
          4. Writes one ``dispute_audit_log`` row per changed field
          5. All within a **single transaction** — no commit between 3 and 4

        Args:
            dispute_id: The dispute to edit.
            changes: Dict of field_name → new_value (only EDITABLE_FIELDS).
            changed_by: Who made the edit ("user" for now).
            note: Optional free-text note.

        Returns:
            List of audit log entries created.

        Raises:
            ValueError: If the dispute is not found or no valid fields provided.
        """
        # 1. Fetch current state
        dispute = await self.get_dispute(dispute_id)
        if dispute is None:
            raise ValueError(f"Dispute {dispute_id} not found")

        # 2. Filter to only editable fields with actual changes
        audit_entries: list[DisputeAuditLog] = []
        update_values: dict[str, Any] = {}

        for field, new_value in changes.items():
            if field not in EDITABLE_FIELDS:
                continue

            old_value = getattr(dispute, field, None)
            old_str = str(old_value) if old_value is not None else None
            new_str = str(new_value) if new_value is not None else None

            if old_str == new_str:
                continue  # No actual change

            update_values[field] = new_value

            entry = DisputeAuditLog(
                dispute_id=dispute_id,
                field=field,
                old_value=old_str,
                new_value=new_str,
                changed_by=changed_by,
                changed_at=datetime.now(timezone.utc),
                note=note,
            )
            self._session.add(entry)
            audit_entries.append(entry)

        if not update_values:
            return []

        # 3 + 4. Update dispute + flush audit logs in same transaction
        update_values["updated_at"] = datetime.now(timezone.utc)
        update_values["updated_by"] = changed_by

        stmt = (
            update(Dispute)
            .where(Dispute.id == dispute_id)
            .values(**update_values)
        )
        await self._session.execute(stmt)

        # Single commit for both the dispute update and all audit log entries
        await self._session.commit()

        logger.info(
            "Updated dispute %s: %d field(s) changed by %s",
            dispute_id, len(audit_entries), changed_by,
        )
        return audit_entries

    async def update_document_id(self, dispute_id: str, document_id: str) -> None:
        """Update the document_id on the dispute record."""
        stmt = (
            update(Dispute)
            .where(Dispute.id == dispute_id)
            .values(
                document_id=document_id,
                updated_at=datetime.now(timezone.utc),
            )
        )
        await self._session.execute(stmt)
        await self._session.commit()
        logger.info("Dispute %s → document_id=%s", dispute_id, document_id)

    async def update_storage_path(self, dispute_id: str, storage_path: str) -> None:
        """Update the storage_path on the dispute record."""
        stmt = (
            update(Dispute)
            .where(Dispute.id == dispute_id)
            .values(
                storage_path=storage_path,
                updated_at=datetime.now(timezone.utc),
            )
        )
        await self._session.execute(stmt)
        await self._session.commit()
        logger.info("Dispute %s → storage_path=%s", dispute_id, storage_path)

    async def update_evidence_pointers(
        self, dispute_id: str, document_id: Optional[str] = None, storage_path: Optional[str] = None
    ) -> None:
        """Update both document_id and storage_path on the dispute record."""
        values: dict[str, Any] = {"updated_at": datetime.now(timezone.utc)}
        if document_id is not None:
            values["document_id"] = document_id
        if storage_path is not None:
            values["storage_path"] = storage_path

        stmt = (
            update(Dispute)
            .where(Dispute.id == dispute_id)
            .values(**values)
        )
        await self._session.execute(stmt)
        await self._session.commit()
        logger.info(
            "Dispute %s → document_id=%s, storage_path=%s",
            dispute_id, document_id, storage_path,
        )

    async def create_evidence_job(self, dispute_id: str) -> EvidenceJob:
        """Enqueue an evidence generation job."""
        job = EvidenceJob(
            dispute_id=dispute_id,
            status="queued",
            attempts=0,
        )
        self._session.add(job)
        await self._session.commit()
        await self._session.refresh(job)
        logger.info("Created EvidenceJob #%d for dispute %s", job.id, dispute_id)
        return job

    async def fetch_next_queued_job(self) -> Optional[EvidenceJob]:
        """Fetch the next queued job with row locking to prevent race conditions."""
        stmt = (
            select(EvidenceJob)
            .where(EvidenceJob.status == "queued")
            .order_by(EvidenceJob.created_at.asc())
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        res = await self._session.execute(stmt)
        return res.scalar_one_or_none()

    async def update_job_status(
        self, job_id: int, status: str, error_message: Optional[str] = None
    ) -> None:
        """Update the status of an evidence job."""
        now = datetime.now(timezone.utc)
        values: dict[str, Any] = {
            "status": status,
            "updated_at": now,
        }
        if status == "processing":
            values["started_at"] = now
            values["attempts"] = EvidenceJob.attempts + 1
        elif status in ("completed", "failed"):
            values["completed_at"] = now
            if error_message:
                values["error_message"] = error_message

        stmt = (
            update(EvidenceJob)
            .where(EvidenceJob.id == job_id)
            .values(**values)
        )
        await self._session.execute(stmt)
        await self._session.commit()
        logger.info("EvidenceJob #%d → status=%s", job_id, status)

    async def get_latest_evidence_job(self, dispute_id: str) -> Optional[EvidenceJob]:
        """Fetch the most recent evidence job for a dispute."""
        stmt = (
            select(EvidenceJob)
            .where(EvidenceJob.dispute_id == dispute_id)
            .order_by(EvidenceJob.created_at.desc())
            .limit(1)
        )
        res = await self._session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_latest_evidence_jobs_map(
        self, dispute_ids: list[str]
    ) -> dict[str, EvidenceJob]:
        """Fetch latest evidence job for multiple disputes in a single query."""
        if not dispute_ids:
            return {}
        stmt = (
            select(EvidenceJob)
            .where(EvidenceJob.dispute_id.in_(dispute_ids))
            .order_by(EvidenceJob.dispute_id, EvidenceJob.created_at.desc())
        )
        res = await self._session.execute(stmt)
        jobs = res.scalars().all()
        result: dict[str, EvidenceJob] = {}
        for j in jobs:
            if j.dispute_id not in result:
                result[j.dispute_id] = j
        return result


