# SafeMerchant Backend — Comprehensive Technical Architecture & Flow Documentation

**Autonomous AI Risk Manager for Payment Disputes & Chargeback Defense**  
*Built for Razorpay Buildathon (Track 2)*  
*Version: 0.2.0 | Python 3.11+ | FastAPI | LangGraph | PostgreSQL | ReportLab | Supabase Storage*

---

## Executive Summary

SafeMerchant is an autonomous, **defense-only agentic risk management system** engineered to ingest, evaluate, evidence, and resolve payment disputes and chargebacks. Built atop FastAPI, SQLAlchemy (AsyncPG), LangGraph, PostgreSQL Checkpointing, ReportLab, and Supabase Storage, the system automates end-to-end dispute triage while strictly enforcing safety boundaries, zero-hallucination evidence verification, and Human-in-the-Loop (HITL) oversight for high-value or ambiguous transactions.

### Key Architectural Characteristics

1. **Defense-Only Safety Invariant**: The system never performs unverified destructive actions or offensive billing operations. It only reads merchant operational databases (orders, shipping, customer chat transcripts, fraud telemetry) and generates bank-compliant evidence packages.
2. **Deterministic Grounding Verification (Zero-Hallucination)**: LLM drafts are verified deterministically against raw database records. Any claim that cannot be traced to exact dotted database keys is dropped before bank submission.
3. **Stateful HITL with Checkpointer Resilience**: LangGraph graphs are compiled with `AsyncPostgresSaver` via `psycopg`. If a dispute requires human review, the workflow pauses at an interrupt breakpoint and state is safely persisted across server restarts.
4. **Asynchronous Evidence Rendering & Job Queue**: Heavy PDF generation and dual cloud uploads (Razorpay Documents API + Supabase Storage) are decoupled from HTTP request paths via a concurrency-capped PostgreSQL job queue (`FOR UPDATE SKIP LOCKED`).
5. **Decoupled OLAP / OLTP Metrics Layer**: Historical metrics, daily summaries, dimensional breakdowns, and audit trails operate independently of live operational state, refreshed incrementally or on demand without heavy table scans.
6. **Real-time Observability via WebSocket Invalidation**: The dashboard WebSocket (`/ws/dashboard`) streams live node progress and lightweight cache invalidation signals (`metrics_stale`), keeping WebSocket traffic minimal and queries in cached REST APIs.

---

## Complete System Architecture Diagram

```
                             ┌───────────────────────────────────┐
                             │    Razorpay Webhook Trigger       │
                             │ (payment.dispute.created payload) │
                             └─────────────────┬─────────────────┘
                                               │ HTTP POST
                                               ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│ FASTAPI INGESTION LAYER (/api/v1/webhook)                                                        │
│  ├─ 1. Write verbatim payload to dispute_events (Immutable Append-Only Log)                      │
│  ├─ 2. Insert/Merge row in disputes (Status: 'processing', Stage: Ingestion)                     │
│  ├─ 3. Background: Increment dispute_metrics_daily (+1 total, +amount at risk)                   │
│  ├─ 4. Broadcast 'dispute_received' via WebSocket (/ws/dashboard)                              │
│  └─ 5. Dispatch BackgroundTask: process_dispute_and_broadcast() -> Return HTTP 202 Accepted     │
└──────────────────────────────────────────────┬───────────────────────────────────────────────────┘
                                               │
                                               ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│ LANGGRAPH STATE MACHINE (AsyncPostgresSaver Checkpointed Thread)                                 │
│                                                                                                  │
│  ┌────────────────────────┐                                                                      │
│  │ SUPER STEP 1           │  Read-Only DB Queries                                                │
│  │ Evidence Retrieval     │ ───────────────────────►  [Orders, Shipping, Comms, Risk Signals]    │
│  └───────────┬────────────┘                                                                      │
│              ▼                                                                                   │
│  ┌────────────────────────┐                                                                      │
│  │ SUPER STEP 2           │  • Heuristic Winnability Scoring (0.0 to 1.0)                        │
│  │ Triage & Scoring       │  • Independent Legitimacy Check (Pre-dispute complaint + no delivery)│
│  └───────────┬────────────┘                                                                      │
│              ▼                                                                                   │
│  ┌────────────────────────┐                                                                      │
│  │ SUPER STEP 3           │  • Step A: Structured Comms Extraction (LLM)                         │
│  │ Response Drafting &    │  • Step B: Grounded Evidence Response Draft (LLM, <=1000 chars)      │
│  │ Grounding Verification │  • Step C: Deterministic Grounding Verifier (Zero LLM, Dotted Keys)  │
│  └───────────┬────────────┘                                                                      │
│              ▼                                                                                   │
│  ┌────────────────────────┐                                                                      │
│  │ CONDITIONAL GATE EDGE  │  Decision matrix based on: Score, Disputed Amount, Legitimacy Signal │
│  └───────────┬────────────┘                                                                      │
│              │                                                                                   │
│   ┌──────────┴──────────────┬────────────────────────┬─────────────────────┬─────────────────┐   │
│   ▼                         ▼                        ▼                     ▼                 ▼   │
│ [auto_submit]        [human_review]            [accept_loss]         [auto_refund]     [refund_review]
│ (Score>=85%,         (Score<85% OR             (Score<30%,           (Legitimate,      (Legitimate,  │
│  Amount<=10k)         Amount>10k)               no legitimacy)        Amount<=10k)      Amount>10k)  │
│   │                         │                        │                     │                 │   │
│   │                  INTERRUPT_BEFORE                │                     │          INTERRUPT_BEFORE
│   │                         │                        │                     │                 │   │
│   ▼                         ▼                        ▼                     ▼                 ▼   │
│ Auto-Enqueue          Awaiting Human           Close Dispute as      Execute Razorpay  Awaiting Review
│ Evidence Job          Review (Resume via REST) Accepted Loss         Refund API        for Refund    │
└─────────────────────────────┬────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│ EVIDENCE WORKER POOL & SUBMISSION PIPELINE (asyncio.Semaphore = 5)                               │
│                                                                                                  │
│  1. Claim queued job via PostgreSQL row locking: SELECT ... FOR UPDATE SKIP LOCKED               │
│  2. ReportLab PDF Generation (Delivery Proof / Chat Transcript / Activity Log)                   │
│  3. Multi-part upload to Razorpay Documents API: POST /v1/documents -> document_id              │
│  4. In-memory stream upload to Supabase Storage: POST /storage/v1/object -> storage_path         │
│  5. Submit contest to Razorpay Disputes API: POST /v1/disputes/{id}/contest                      │
│  6. Classify Response:                                                                           │
│     - HTTP 200/201/204: status = 'under_review'                                                  │
│     - HTTP 400/404 (Sandbox limitation): status = 'under_review', job = contest_expected_failure │
│     - Other 4xx/5xx: status = 'error', raise DisputeSubmissionError                              │
│  7. Update submission logs, dispute history, and broadcast execution completed via WebSocket     │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## Component Deep Dive

### 1. Ingestion & Webhook Layer (`app/dispute/routes.py`, `app/dispute/schemas/webhook.py`)
- **Endpoint**: `POST /api/v1/webhook`
- **Validation**: Enforces strict Pydantic parsing of nested payloads:
  - `payload.dispute.entity`: `id`, `payment_id`, `amount`, `reason_code`, `phase`, `created_at`
  - `payload.payment.entity`: `id`, `amount`, `order_id`, `email`, `status`
- **Two-Phase Commit Pattern ("Top Bun / Bottom Bun")**:
  1. *Top Bun*: Single fast DB session inserts raw event into `dispute_events` and initializes `disputes`. Broadcasts `dispute_received` over WebSocket.
  2. *LangGraph Pipeline*: Runs asynchronously without holding open DB connections.
  3. *Bottom Bun*: Final DB session updates `disputes` status, enqueues evidence generation jobs if contested, records history events, and triggers metrics updates.

### 2. State & LangGraph Orchestration Engine (`app/dispute/agent/`)
- **State Schema (`DisputeAgentState`)**: Central TypedDict tracking 35+ fields through stages:
  - Stage 0 (Ingestion): `dispute_id`, `payment_id`, `order_id`, `reason_code`, `disputed_amount_inr`, `customer_email`, `dispute_phase`
  - Stage 1 (Evidence): `evidence_bundle`, `evidence_collected_at`, `evidence_summary`
  - Stage 2 (Triage): `winnability_score`, `risk_factors`, `triage_reasoning`, `recommended_action`, `customer_legitimacy_signal`, `legitimacy_reasoning`
  - Stage 3 (Drafting): `comms_extraction`, `draft_summary`, `draft_explanation_letter`, `draft_evidence_fields`, `verification_report`, `verified_explanation_letter`, `verified_evidence_fields`
  - Gate & Resolution: `gate_action`, `requires_human_review`, `human_review_reason`, `refund_id`, `refund_status`, `case_resolution`
  - Observability: `current_node`, `node_history`, `messages`, `error`

- **Super Step 1 — Evidence Retrieval (`nodes/super_step_1.py`)**:
  - Executes read-only queries via `EvidenceRepository` eager-loading:
    - `orders`: `amount_inr`, `item_description`, `customer_email`, `created_at`
    - `shipping_logs`: `tracking_id`, `courier_partner`, `delivery_status`, `signed_by`, `delivery_timestamp`
    - `customer_communications`: `ticket_id`, `channel`, `message_transcript`, `logged_at`
    - `risk_signals`: `ip_address`, `device_fingerprint`, `is_2fa_verified`, `account_age_days`

- **Super Step 2 — Triage & Scoring (`nodes/super_step_2.py`)**:
  - Computes base winnability score from evidence features:
    - Delivery Proof Delivered (+0.25), Signed By (+0.10), Missing delivery proof (-0.20)
    - 2FA Verified (+0.10), Missing 2FA (-0.05)
    - Customer Communications present (+0.05), Missing (-0.05)
  - Independent Customer Legitimacy Assessment:
    - Checks if communications were logged prior to dispute filing date (`_has_complaint_before_dispute`).
    - If customer lodged pre-dispute complaints and delivery proof is missing, `customer_legitimacy_signal` is set to `True`, recommending `refund_customer`.

- **Super Step 3 — Response Drafting & Verification (`nodes/super_step_3.py`)**:
  - **Step A**: LLM extracts structured facts (`CommsExtraction`) verifying product receipt acknowledgement, prior complaints, and verbatim quotes.
  - **Step B**: LLM generates structured draft (`DraftOutput`) adhering to reason code mapping (`REASON_CODE_EVIDENCE_MAP`) and Razorpay's 1000-character letter limit.
  - **Step C**: `verify_grounding()` inspects each factual claim's `source_key` (e.g., `shipping.delivery_status`) against raw dictionary values. Claims with unresolvable keys or mismatched values are dropped. `rebuild_letter_from_verified_fields()` constructs a clean explanation letter from verified facts only.

- **Gate Decision & Routing Matrix (`nodes/gate.py`)**:
  | Condition | Disputed Amount | Recommended Action | Next Node / Action |
  | :--- | :--- | :--- | :--- |
  | Legitimacy Flag = True | $\le$ ₹10,000 | `refund_customer` | `auto_refund` (Calls Razorpay Refund API) |
  | Legitimacy Flag = True | $>$ ₹10,000 | `refund_customer` | `refund_review` (HITL Interrupt) |
  | Score $\ge$ 85% | $\le$ ₹10,000 | `contest` | `auto_submit` (Enqueues Evidence Job) |
  | Score $<$ 85% OR Amount $>$ 10k | Any | `contest` | `human_review` (HITL Interrupt) |
  | Score $<$ 30% (No Legitimacy) | Any | `accept_loss` | `accept_loss` (Resolves as Accepted Loss) |

### 3. Human-in-the-Loop (HITL) Workflow
- When the graph hits `human_review` or `refund_review`, execution halts due to `interrupt_before`.
- State is checkpointed in PostgreSQL (`checkpoints`, `checkpoint_blobs`, `checkpoint_writes`).
- The dispute status changes to `awaiting_review`, and `human_review_required` is broadcast to clients.
- Reviewers submit decisions via `POST /api/v1/disputes/{id}/review`:
  - `accept`: Resumes graph, contest/refund proceeds, enqueues background job.
  - `reject`: Resumes graph, marks dispute as `resolved_accepted_loss`.
  - Supports custom partial contest amounts (`amount_paise`).

### 4. Asynchronous Evidence Worker & Submission Pipeline (`app/dispute/worker.py`, `app/dispute/submission.py`)
- **Worker Pool**: `EvidenceWorkerPool` runs with `asyncio.Semaphore(5)`.
- **Atomic Job Claiming**: Executes `SELECT ... FROM evidence_jobs WHERE status = 'queued' ORDER BY created_at ASC LIMIT 1 FOR UPDATE SKIP LOCKED`.
- **ReportLab Rendering Engine (`app/proof_renderer/`)**:
  - `ChargebackPDFRenderer`: Compiles pure in-memory PDF documents with zero disk IO.
  - Generates comprehensive evidence layouts:
    - Delivery Confirmation & Logistics Timeline
    - Shipping Address vs. Billing Address Verification (with automated mismatch warning alerts)
    - 2FA / OTP Verification Reference IDs & delivery verification timestamps
    - Carrier tracking timeline events
    - Payment Security & Device Fingerprint Telemetry
    - Prior successful delivery history table
- **Dual Cloud Upload Strategy**:
  1. Uploads in-memory stream to Razorpay Documents API (`POST /v1/documents`), acquiring `document_id`.
  2. Uploads stream to private Supabase Storage bucket (`evidence-pdfs/{dispute_id}/evidence.pdf`).
  3. Dispatches contest payload to Razorpay Disputes Contest API (`PATCH /v1/disputes/{id}/contest`).
  4. Handles sandbox limitations gracefully: If Razorpay sandbox returns expected 400/404 ("dispute does not exist"), logs `contest_expected_failure`, updates dispute to `under_review`, and stores evidence pointers.
- **Signed URL Access**: `GET /api/v1/disputes/{id}/evidence-url` generates short-lived Supabase signed URLs (1 hour expiry) for direct CDN preview in the frontend.

### 5. Metrics & Transactional Auditing Layer (`app/dispute/metrics_repository.py`, `app/dispute/metrics_service.py`)
- **Data Models**:
  - `dispute_events`: Verbatim append-only raw webhook logs.
  - `dispute_audit_log`: Logs every field change from human edits via `PATCH /api/v1/disputes/{id}` in the same database transaction.
  - `dispute_metrics_daily`: Aggregated daily metrics (`total_disputes`, `won`, `lost`, `action_required`, `amount_won_paise`, `amount_lost_paise`, `amount_at_risk_paise`, `sla_breached`).
  - `dispute_breakdowns`: Materialized aggregations by `reason_code`, `outcome`, and `phase`.
- **REST Endpoints**:
  - `GET /api/v1/metrics/summary?from=YYYY-MM-DD&to=YYYY-MM-DD`
  - `GET /api/v1/metrics/breakdown?by=reason_code|outcome|phase`
  - `GET /api/v1/metrics/repeat-patterns?min_count=2`
  - `PATCH /api/v1/disputes/{id}` (human dispute edits)
  - `GET /api/v1/disputes/{id}/audit` (audit trail)

### 6. Real-Time Observability (`app/dispute/websocket.py`)
- **WebSocket Endpoint**: `/ws/dashboard`
- **Broadcast Events**:
  - `dispute_received`: Immediate notification of incoming webhook
  - `node_update`: Real-time streaming of LangGraph node execution
  - `human_review_required`: Paused state notification
  - `review_submitted`: Notification that a human review has been recorded
  - `job_picked_up`, `evidence_completed`, `evidence_job_failed`: Evidence background worker updates
  - `execution_completed`: Terminal status reached
  - `metrics_stale`: Cache invalidation signal (`scope: daily_summary | breakdown | all`)
  - `database_reset`: System wipe notification

---

## Complete Database Schema Summary

| Table | Purpose | Write Pattern | Key Columns |
| :--- | :--- | :--- | :--- |
| `orders` | Read-only merchant ledger | Read-Only | `order_id` (PK), `payment_id`, `customer_email`, `amount_inr`, `item_description` |
| `shipping_logs` | Logistics delivery proof | Read-Only | `tracking_id` (PK), `order_id` (FK), `courier_partner`, `delivery_status`, `signed_by`, `delivery_timestamp` |
| `customer_communications` | Customer support transcripts | Read-Only | `ticket_id` (PK), `order_id` (FK), `channel`, `message_transcript`, `logged_at` |
| `risk_signals` | Fraud & security telemetry | Read-Only | `signal_id` (PK), `order_id` (FK), `ip_address`, `device_fingerprint`, `is_2fa_verified`, `account_age_days` |
| `disputes` | Mutable operational dispute record | System + HITL Writable | `id` (PK), `status`, `amount_paise`, `reason_code`, `customer_email`, `payment_id`, `order_id`, `document_id`, `storage_path`, `phase`, `outcome`, `history` (JSONB) |
| `evidence_jobs` | Background PDF & upload queue | Worker Queue | `id` (PK), `dispute_id` (FK), `status` (`queued`, `processing`, `completed`, `failed`), `attempts`, `error_message` |
| `dispute_events` | Immutable raw webhook log | Append-Only | `id` (PK), `dispute_id`, `event_type`, `payload` (JSONB), `occurred_at` |
| `dispute_audit_log` | Transactional audit log of human edits | Append-Only | `id` (PK), `dispute_id` (FK), `field`, `old_value`, `new_value`, `changed_by`, `changed_at`, `note` |
| `dispute_submission_log` | Outbound Razorpay submission log | Append-Only | `id` (PK), `dispute_id` (FK), `document_id`, `document_upload_status`, `contest_status`, `outcome`, `error_message` |
| `dispute_metrics_daily` | Pre-aggregated daily metrics | Incremental Upsert | `date` (PK), `total_disputes`, `won`, `lost`, `action_required`, `amount_won_paise`, `amount_lost_paise`, `amount_at_risk_paise`, `sla_breached` |
| `dispute_breakdowns` | Pre-computed dimensional counts | Full Refresh | `id` (PK), `dimension`, `dimension_value`, `count`, `amount_paise`, `refreshed_at` |
| `checkpoints` / `checkpoint_blobs` / `checkpoint_writes` | LangGraph state checkpoints | LangGraph Managed | Thread ID persistence for HITL workflow interruption and resumption |

---

## Verification & Evaluation Framework (`backend/evaluation/`)

The backend includes a comprehensive evaluation and chaos testing suite:
- **Synthetic Dispute Generator (`synthetic_disputes.py`)**: Generates realistic dispute scenarios across 6 distinct profiles:
  - Strong delivery evidence (Auto-submit candidates)
  - Clear merchant fraud/scam (Customer legitimacy refund candidates)
  - High-value transactions > ₹10k (Human review candidates)
  - Borderline winnability 40-70% (Human review candidates)
  - No shipping records / lost cases (Accept loss candidates)
  - Subscription cancellation disputes
- **Evaluation Runner & Metrics Engine (`runner.py`, `metrics.py`)**: Runs batches through the pipeline and calculates:
  - Classification Accuracy & Per-class Precision, Recall, F1 Scores
  - Confusion Matrix across gate decisions (`auto_submit`, `human_review`, `accept_loss`, `auto_refund`, `refund_review`)
  - False Positive Cost Metrics (calculates monetary impact of contesting illegitimate claims or incorrectly refunding legitimate transactions)
  - Automated Markdown evaluation report generator (`report_template.md`)
