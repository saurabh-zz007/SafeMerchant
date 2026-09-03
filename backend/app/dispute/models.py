"""
SQLAlchemy ORM models for the merchant evidence database.

These map 1:1 to the tables defined in relationalDBschema.txt:
  - orders              → Order
  - shipping_logs       → ShippingLog
  - customer_communications → CustomerCommunication
  - risk_signals        → RiskSignal

All models are READ-ONLY from the agent's perspective.
The agent never inserts, updates, or deletes merchant data.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class Order(Base):
    """Core orders ledger — the anchor for all evidence."""

    __tablename__ = "orders"

    order_id: Mapped[str] = mapped_column(
        String(50), primary_key=True
    )
    payment_id: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False
    )
    customer_email: Mapped[str] = mapped_column(
        String(100), nullable=False
    )
    amount_inr: Mapped[int] = mapped_column(
        Integer, nullable=False
    )
    item_description: Mapped[str] = mapped_column(
        Text, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default="CURRENT_TIMESTAMP"
    )

    # ── Relationships ──
    shipping_logs: Mapped[list["ShippingLog"]] = relationship(
        back_populates="order", cascade="all, delete-orphan", lazy="selectin"
    )
    communications: Mapped[list["CustomerCommunication"]] = relationship(
        back_populates="order", cascade="all, delete-orphan", lazy="selectin"
    )
    risk_signals: Mapped[list["RiskSignal"]] = relationship(
        back_populates="order", cascade="all, delete-orphan", lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<Order {self.order_id} ₹{self.amount_inr}>"


class ShippingLog(Base):
    """Physical logistics & delivery evidence."""

    __tablename__ = "shipping_logs"

    tracking_id: Mapped[str] = mapped_column(
        String(50), primary_key=True
    )
    order_id: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("orders.order_id", ondelete="CASCADE"),
        nullable=False,
    )
    courier_partner: Mapped[str] = mapped_column(
        String(50), nullable=False
    )
    delivery_status: Mapped[str] = mapped_column(
        String(50), nullable=False
    )
    signed_by: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True
    )
    delivery_timestamp: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # ── Relationships ──
    order: Mapped["Order"] = relationship(back_populates="shipping_logs", lazy="selectin")

    def __repr__(self) -> str:
        return f"<ShippingLog {self.tracking_id} → {self.delivery_status}>"


class CustomerCommunication(Base):
    """Customer interaction transcripts — email, WhatsApp, chat."""

    __tablename__ = "customer_communications"

    ticket_id: Mapped[str] = mapped_column(
        String(50), primary_key=True
    )
    order_id: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("orders.order_id", ondelete="CASCADE"),
        nullable=False,
    )
    channel: Mapped[str] = mapped_column(
        String(20), nullable=False
    )
    message_transcript: Mapped[str] = mapped_column(
        Text, nullable=False
    )
    logged_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default="CURRENT_TIMESTAMP"
    )

    # ── Relationships ──
    order: Mapped["Order"] = relationship(back_populates="communications", lazy="selectin")

    def __repr__(self) -> str:
        return f"<Communication {self.ticket_id} via {self.channel}>"


class RiskSignal(Base):
    """Authentication & network telemetry signals."""

    __tablename__ = "risk_signals"

    signal_id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    order_id: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("orders.order_id", ondelete="CASCADE"),
        nullable=False,
    )
    ip_address: Mapped[str] = mapped_column(
        String(50), nullable=False
    )
    device_fingerprint: Mapped[str] = mapped_column(
        String(100), nullable=False
    )
    is_2fa_verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    account_age_days: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )

    # ── Relationships ──
    order: Mapped["Order"] = relationship(back_populates="risk_signals", lazy="selectin")

    def __repr__(self) -> str:
        return f"<RiskSignal #{self.signal_id} 2FA={self.is_2fa_verified}>"


# ═══════════════════════════════════════════════════════════════════
# DISPUTE LIFECYCLE — writable model for HITL tracking
# ═══════════════════════════════════════════════════════════════════

class Dispute(Base):
    """
    Tracks the lifecycle of a payment dispute through the agent pipeline.

    Unlike the evidence tables above (read-only), this model is written to
    by the HITL flow: status transitions, webhook payloads, node outcomes,
    and human review decisions are all persisted in the ``history`` JSONB column.
    """

    __tablename__ = "disputes"

    id: Mapped[str] = mapped_column(
        String(100), primary_key=True,
        comment="Razorpay dispute ID (e.g., disp_XXXX)",
    )
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, server_default="processing",
        comment="processing | awaiting_review | resolved | error",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default="CURRENT_TIMESTAMP",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default="CURRENT_TIMESTAMP",
        onupdate=datetime.utcnow,
    )
    history: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default="'[]'::jsonb",
        comment="Chronological log: webhook payload, node outcomes, review decisions",
    )

    # ── Metrics-relevant columns (added by 002_metrics_schema) ──
    amount_paise: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True,
        comment="Disputed amount in paise (integer, not float)",
    )
    amount_deducted: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, server_default="0",
        comment="Amount deducted in paise (from Razorpay dispute entity)",
    )
    respond_by: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
        comment="Dispute response deadline (from Razorpay respond_by timestamp)",
    )
    reason_code: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True,
        comment="Dispute reason: chargeback | fraud | item_not_received | etc.",
    )
    customer_email: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True,
    )
    payment_id: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True,
        comment="Razorpay payment ID (e.g., pay_XYZ1001)",
    )
    order_id: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True,
        comment="Merchant order ID (e.g., ORD_1001)",
    )
    document_id: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True,
        comment="Razorpay document ID (e.g., doc_XXXX)",
    )
    storage_path: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True,
        comment="Supabase Storage path (e.g., evidence-pdfs/disp_XXXX/evidence.pdf)",
    )
    phase: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True, server_default="chargeback",
        comment="chargeback | pre_arbitration | arbitration",
    )
    outcome: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True, server_default="open",
        comment="won | lost | open | accepted_loss",
    )
    updated_by: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True, server_default="system",
        comment="'system' for webhook/agent, 'user' for manual edits",
    )
    webhook_received_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
        comment="Timestamp when the webhook was first ingested",
    )
    resolved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
        comment="Timestamp when dispute reached terminal state",
    )
    review_context: Mapped[Optional[dict]] = mapped_column(
        JSONB, nullable=True,
        comment="Persisted AI brief and triage context for HITL review",
    )

    # ── Relationships ──
    audit_logs: Mapped[list["DisputeAuditLog"]] = relationship(
        back_populates="dispute", cascade="all, delete-orphan", lazy="select"
    )
    submission_logs: Mapped[list["DisputeSubmissionLog"]] = relationship(
        back_populates="dispute", cascade="all, delete-orphan", lazy="select"
    )
    evidence_jobs: Mapped[list["EvidenceJob"]] = relationship(
        back_populates="dispute", cascade="all, delete-orphan", lazy="select"
    )

    def __repr__(self) -> str:
        return f"<Dispute {self.id} status={self.status}>"


# ═══════════════════════════════════════════════════════════════════
# EVIDENCE GENERATION JOB QUEUE
# ═══════════════════════════════════════════════════════════════════

class EvidenceJob(Base):
    """
    Tracks queued asynchronous evidence PDF generation and upload tasks.
    """
    __tablename__ = "evidence_jobs"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True,
    )
    dispute_id: Mapped[str] = mapped_column(
        String(100), ForeignKey("disputes.id", ondelete="CASCADE"),
        nullable=False, index=True,
        comment="Dispute to generate evidence for",
    )
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, server_default="queued", index=True,
        comment="queued | processing | completed | failed",
    )
    attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0",
        comment="Number of times this job has been attempted",
    )
    max_attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="3",
        comment="Maximum allowed retry attempts",
    )
    error_message: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True,
        comment="Last error message if job failed",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default="CURRENT_TIMESTAMP",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default="CURRENT_TIMESTAMP",
        onupdate=datetime.utcnow,
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    dispute: Mapped["Dispute"] = relationship(
        back_populates="evidence_jobs", lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<EvidenceJob id={self.id} dispute_id={self.dispute_id} status={self.status}>"


# ═══════════════════════════════════════════════════════════════════
# DISPUTE EVENTS — append-only immutable raw event log
# ═══════════════════════════════════════════════════════════════════

class DisputeEvent(Base):
    """
    Append-only, immutable raw event log.

    Every webhook payload received gets a row here, verbatim, with
    ``occurred_at``.  This is the source of truth for replay/backfill
    if a metrics table ever needs to be rebuilt.

    NEVER update or delete rows in this table.
    """

    __tablename__ = "dispute_events"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True,
    )
    dispute_id: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True,
    )
    event_type: Mapped[str] = mapped_column(
        String(50), nullable=False,
    )
    payload: Mapped[dict] = mapped_column(
        JSONB, nullable=False,
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="CURRENT_TIMESTAMP",
    )

    def __repr__(self) -> str:
        return f"<DisputeEvent {self.id} type={self.event_type}>"


# ═══════════════════════════════════════════════════════════════════
# DISPUTE AUDIT LOG — append-only log of manual edits
# ═══════════════════════════════════════════════════════════════════

class DisputeAuditLog(Base):
    """
    Append-only log of every manual edit made to a ``disputes`` row.

    Any edit endpoint MUST write to this table in the same DB transaction
    as the update to ``disputes`` — never allow a raw update without an
    audit row.
    """

    __tablename__ = "dispute_audit_log"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True,
    )
    dispute_id: Mapped[str] = mapped_column(
        String(100),
        ForeignKey("disputes.id"),
        nullable=False,
    )
    field: Mapped[str] = mapped_column(
        String(100), nullable=False,
    )
    old_value: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True,
    )
    new_value: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True,
    )
    changed_by: Mapped[str] = mapped_column(
        String(100), nullable=False, server_default="user",
    )
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="CURRENT_TIMESTAMP",
    )
    note: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True,
    )

    # ── Relationships ──
    dispute: Mapped["Dispute"] = relationship(back_populates="audit_logs", lazy="selectin")

    def __repr__(self) -> str:
        return f"<AuditLog dispute={self.dispute_id} field={self.field}>"


# ═══════════════════════════════════════════════════════════════════
# DISPUTE SUBMISSION LOG — log of outbound submissions
# ═══════════════════════════════════════════════════════════════════

class DisputeSubmissionLog(Base):
    """
    Dedicated log table for storing outbound dispute evidence submissions.
    """
    __tablename__ = "dispute_submission_log"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True,
    )
    dispute_id: Mapped[str] = mapped_column(
        String(100),
        ForeignKey("disputes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default="CURRENT_TIMESTAMP",
        nullable=False,
    )
    document_id: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True,
    )
    document_upload_payload: Mapped[Optional[dict]] = mapped_column(
        JSONB, nullable=True,
    )
    document_upload_status: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True,
    )
    document_upload_response: Mapped[Optional[dict]] = mapped_column(
        JSONB, nullable=True,
    )
    contest_payload: Mapped[Optional[dict]] = mapped_column(
        JSONB, nullable=True,
    )
    contest_status: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True,
    )
    contest_response: Mapped[Optional[dict]] = mapped_column(
        JSONB, nullable=True,
    )
    outcome: Mapped[str] = mapped_column(
        String(50), nullable=False,
        comment="success | api_rejected_expected | submission_failed",
    )
    error_message: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True,
    )

    # ── Relationships ──
    dispute: Mapped["Dispute"] = relationship(back_populates="submission_logs", lazy="selectin")

    def __repr__(self) -> str:
        return f"<SubmissionLog dispute={self.dispute_id} outcome={self.outcome}>"


# ═══════════════════════════════════════════════════════════════════
# DISPUTE METRICS DAILY — pre-aggregated daily metrics
# ═══════════════════════════════════════════════════════════════════

class DisputeMetricsDaily(Base):
    """
    One row per calendar day, pre-aggregated.

    This is what trend charts read from — never compute trends by
    scanning ``disputes`` live.
    """

    __tablename__ = "dispute_metrics_daily"

    date: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), primary_key=True,
        comment="Calendar date (no timezone, just DATE)",
    )
    total_disputes: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0",
    )
    won: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0",
    )
    lost: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0",
    )
    action_required: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0",
    )
    amount_won_paise: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0",
    )
    amount_lost_paise: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0",
    )
    amount_at_risk_paise: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0",
    )
    avg_response_seconds: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True,
    )
    sla_breached: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0",
    )

    def __repr__(self) -> str:
        return f"<MetricsDaily {self.date} total={self.total_disputes}>"


# ═══════════════════════════════════════════════════════════════════
# DISPUTE BREAKDOWNS — aggregation table (materialized view equiv.)
# ═══════════════════════════════════════════════════════════════════

class DisputeBreakdown(Base):
    """
    Current-state breakdowns that don't need daily granularity.

    Dimensions: ``reason_code``, ``outcome``, ``phase``.
    Refreshed on a schedule or triggered after event ingestion —
    NOT on every dashboard page load.
    """

    __tablename__ = "dispute_breakdowns"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True,
    )
    dimension: Mapped[str] = mapped_column(
        String(50), nullable=False,
    )
    dimension_value: Mapped[str] = mapped_column(
        String(100), nullable=False,
    )
    count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0",
    )
    amount_paise: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0",
    )
    refreshed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="CURRENT_TIMESTAMP",
    )

    def __repr__(self) -> str:
        return f"<Breakdown {self.dimension}={self.dimension_value} count={self.count}>"
