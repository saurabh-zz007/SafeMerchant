"""
LangGraph TypedDict state schema — the central data envelope
that flows through every node in the dispute-resolution graph.

                 ┌─────────────┐
                 │  Webhook    │
                 │  Ingestion  │
                 └──────┬──────┘
                        ▼
              ┌─────────────────┐
              │  Node 1:        │
              │  Evidence       │
              │  Retrieval      │
              └────────┬────────┘
                       ▼
              ┌─────────────────┐
              │  Node 2:        │
              │  Triage &       │
              │  Score          │
              └────────┬────────┘
                       ▼
              ┌─────────────────┐
              │  Node 3:        │
              │  Draft          │
              │  Response       │
              └────────┬────────┘
                       ▼
              ┌─────────────────┐
              │  Conditional    │
              │  Gate Edge      │
              │  (auto / HITL)  │
              └─────────────────┘
"""

from __future__ import annotations

from typing import Optional, TypedDict


class EvidenceBundle(TypedDict, total=False):
    """
    Structured evidence gathered from merchant database.
    Mirrors the return schema of the fetch_dispute_evidence tool
    defined in agentToolDefinition.txt.
    """

    order: dict          # order_id, payment_id, customer_email, amount_inr, item_description, created_at
    shipping: dict | None        # tracking_id, courier_partner, delivery_status, signed_by, delivery_timestamp
    communications: list[dict]   # [{ticket_id, channel, message_transcript, logged_at}, ...]
    risk_signals: dict | None    # ip_address, device_fingerprint, is_2fa_verified, account_age_days


class DisputeAgentState(TypedDict, total=False):
    """
    The complete state envelope for the dispute-resolution LangGraph.

    Every node reads from and writes to this TypedDict. Fields are grouped
    by the pipeline stage that populates them.

    DEFENSE-ONLY INVARIANT:
      This state never contains offensive actions, write-back mutations,
      or payment execution commands. The agent can only READ evidence
      and RECOMMEND a response.
    """

    # ═══════════════════════════════════════════════════════════════════
    # STAGE 0 — INGESTION (populated by webhook handler)
    # ═══════════════════════════════════════════════════════════════════
    dispute_id: str                  # Razorpay dispute ID (e.g., "disp_XXXX")
    payment_id: str                  # Razorpay payment ID (e.g., "pay_XYZ1001")
    order_id: str                    # Merchant order ID (e.g., "ORD_1001")
    reason_code: str                 # Dispute reason: "chargeback" | "fraud" | "product_not_received" | ...
    disputed_amount_inr: int         # Amount in paisa or INR (matches orders.amount_inr)
    dispute_phase: str               # "chargeback" | "pre_arbitration" | "arbitration"
    customer_email: str              # Customer who raised the dispute
    dispute_created_at: Optional[int]  # Unix timestamp of dispute creation (from webhook)

    # ═══════════════════════════════════════════════════════════════════
    # STAGE 1 — EVIDENCE RETRIEVAL (populated by Node 1)
    # ═══════════════════════════════════════════════════════════════════
    evidence_bundle: Optional[EvidenceBundle]  # Full evidence from merchant DB
    evidence_collected_at: Optional[str]       # ISO timestamp of evidence retrieval
    evidence_summary: Optional[str]            # LLM-generated plain-English summary

    # ═══════════════════════════════════════════════════════════════════
    # STAGE 2 — TRIAGE & SCORING (populated by Node 2)
    # ═══════════════════════════════════════════════════════════════════
    winnability_score: Optional[float]         # 0.0 – 1.0 (0% – 100% win probability)
    risk_factors: list[str]                    # List of identified risk signals
    triage_reasoning: Optional[str]            # LLM chain-of-thought reasoning
    recommended_action: Optional[str]          # "contest" | "accept_loss" | "partial_refund" | "refund_customer"
    customer_legitimacy_signal: bool           # True if evidence shows customer is right
    legitimacy_reasoning: Optional[str]        # Why legitimacy was flagged

    # ═══════════════════════════════════════════════════════════════════
    # STAGE 3 — DRAFT RESPONSE (populated by Node 3)
    # ═══════════════════════════════════════════════════════════════════
    # Step A: Structured extraction from communications
    comms_extraction: Optional[dict]           # {"acknowledged_receipt": bool, "complaint_before_dispute": bool, "relevant_quote_ref": str}

    # Step B: LLM draft output
    draft_summary: Optional[str]               # Short-form summary
    draft_explanation_letter: Optional[str]     # ≤1000 chars, per Razorpay field limit
    draft_evidence_fields: Optional[dict]      # {field_name: {facts: [...], source_keys: [...]}}

    # Step C: Grounding verification output
    verification_report: Optional[dict]        # {kept: [...], dropped: [...]}
    verified_explanation_letter: Optional[str]  # Post-verification letter (only verified facts)
    verified_evidence_fields: Optional[dict]   # Post-verification evidence fields

    # Legacy / simple
    draft_response_letter: Optional[str]       # Bank-compliant evidence letter (markdown)
    cited_evidence_keys: list[str]             # Which evidence fields were cited in the letter

    # ═══════════════════════════════════════════════════════════════════
    # GATE — CONDITIONAL EDGE DECISION
    # ═══════════════════════════════════════════════════════════════════
    gate_action: Optional[str]                 # "auto_submit" | "human_review" | "accept_loss" | "auto_refund" | "refund_review"
    requires_human_review: bool                # True if the gate decided HITL is needed
    human_review_reason: Optional[str]         # Why the gate triggered human review
    refund_id: Optional[str]                   # Razorpay refund ID if refund was executed
    refund_status: Optional[str]               # "initiated" | "processed" | "failed"
    case_resolution: Optional[str]             # "resolved_contested" | "resolved_refunded" | "resolved_accepted_loss" | "pending_review"

    # ═══════════════════════════════════════════════════════════════════
    # HUMAN-IN-THE-LOOP — populated by the resume endpoint
    # ═══════════════════════════════════════════════════════════════════
    user_decision: Optional[dict]              # {"action": "accept"|"reject", "reason": "..."}

    # ═══════════════════════════════════════════════════════════════════
    # OBSERVABILITY — REAL-TIME STATE FOR WEBSOCKET STREAMING
    # ═══════════════════════════════════════════════════════════════════
    current_node: Optional[str]                # Name of the currently executing node
    node_history: list[str]                    # Chronological list of all visited nodes
    messages: list[dict]                       # Agent reasoning messages (for WS streaming)
    error: Optional[str]                       # Error message if any node fails
