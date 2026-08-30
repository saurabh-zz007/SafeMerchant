# SafeMerchant Backend — Autonomous AI Risk Manager

> Defense-only agentic system for automated chargeback dispute resolution.
> Built for the Razorpay Buildathon (Track 2).

## Quick Start

### 1. Prerequisites

- Python 3.11+
- PostgreSQL 14+ (running locally or via Docker)

### 2. Setup

```bash
# Create virtual environment
python -m venv .venv
.venv\Scripts\activate  # Windows

# Install dependencies
pip install -e .

# Copy environment config
copy .env.example .env
# Edit .env with your database URL and API keys
```

### 3. Database Setup

```bash
# Create the database
psql -U postgres -c "CREATE DATABASE safemerchant;"

# Run the migration (schema + seed data)
psql -U postgres -d safemerchant -f migrations/001_initial_schema.sql
```

### 4. Run the Server

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 5. Test the Webhook

```bash
curl -X POST http://localhost:8000/api/v1/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "event": "payment.dispute.created",
    "payload": {
      "entity": {
        "id": "disp_001",
        "payment_id": "pay_XYZ1001",
        "amount": 52976,
        "reason_code": "chargeback",
        "phase": "chargeback"
      }
    }
  }'
```

### 6. Chaos Test

```bash
python -m tests.run_test_batch --url http://localhost:8000/api/v1/webhook --count 100
```

## Architecture

```
Webhook → FastAPI → LangGraph Pipeline → Gate Decision
                        │
            ┌───────────┼───────────┐
            ▼           ▼           ▼
        Evidence    Triage &    Draft
        Retrieval   Score       Response
            │           │           │
            └───────────┼───────────┘
                        ▼
                  Gate Decision
              ┌─────────┼─────────┐
              ▼         ▼         ▼
          Auto       Human     Accept
          Submit     Review    Loss
```

## Project Structure

```
backend/
├── app/
│   ├── main.py           # FastAPI app factory
│   ├── config.py          # Pydantic Settings
│   ├── agent/             # LangGraph state, nodes, graph, tools
│   ├── db/                # SQLAlchemy models, engine, repository
│   ├── schemas/           # Pydantic validation models
│   ├── api/               # REST + WebSocket routes
│   └── services/          # Dispute orchestration
├── migrations/            # SQL DDL + seed data
├── tests/                 # Chaos testing
└── pyproject.toml         # Dependencies
```

## Metrics Backend

SafeMerchant includes a production-grade metrics layer that is historical, queryable, auditable, and editable — **separate from the live operational state**.

### Data Model

| Table | Purpose | Mutability |
|-------|---------|------------|
| `dispute_events` | Append-only raw event log (every webhook payload verbatim) | **Immutable** — UPDATE/DELETE blocked by DB trigger |
| `disputes` | Mutable operational record (current status, amount, reason, workflow) | Writable (system + human edits) |
| `dispute_audit_log` | Append-only log of every manual edit to `disputes` | **Append-only** — one row per changed field per edit |
| `dispute_metrics_daily` | Pre-aggregated daily metrics (one row per calendar day) | Upserted by metrics service |
| `dispute_breakdowns` | Current-state breakdowns by dimension (reason_code, outcome, phase) | Full-refreshed on event ingestion |

### Metrics Refresh Strategy

```
Webhook received
  │
  ├─ 1. INSERT into dispute_events (immutable, always first)
  ├─ 2. INSERT/MERGE into disputes (with metrics columns)
  ├─ 3. Incremental UPSERT to dispute_metrics_daily for today
  │     (INSERT ... ON CONFLICT DO UPDATE — adds deltas)
  ├─ 4. Full refresh of dispute_breakdowns
  │     (DELETE + re-INSERT from disputes, single transaction)
  └─ 5. WebSocket: broadcast { type: "metrics_stale", scope: "all" }
```

- **On ingestion**: +1 total disputes, +amount to at-risk
- **On resolution**: Move from at-risk to won/lost, increment won/lost counters
- **On human edit (PATCH)**: Refresh breakdowns only (daily metrics unaffected by single-field edits)
- **Full recomputation**: Available via `recompute_daily_metrics_background(date)` for backfill scenarios

### Metrics API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/metrics/summary?from=&to=` | GET | Aggregated totals from `dispute_metrics_daily` |
| `/api/v1/metrics/breakdown?by=reason_code\|outcome\|phase` | GET | Current breakdown from `dispute_breakdowns` |
| `/api/v1/metrics/repeat-patterns` | GET | Repeat customer/email patterns |
| `/api/v1/disputes/{id}` | PATCH | Human edit with transactional audit logging |
| `/api/v1/disputes/{id}/audit` | GET | Audit trail for one dispute |

### WebSocket Invalidation

The WebSocket (`/ws/dashboard`) does **NOT** push metrics payloads. Instead, it sends a small invalidation signal:

```json
{ "type": "metrics_stale", "scope": "daily_summary" }
```

The frontend should react by invalidating the relevant cache key and refetching from the REST metrics endpoints. This keeps the socket cheap and keeps metrics queries (date ranges, filters, pagination) in request/response APIs where they belong.

### Audit Trail

Every human edit via `PATCH /disputes/{id}` writes to `dispute_audit_log` in the **same DB transaction** as the `disputes` update. There is no code path that modifies a dispute via the edit endpoint without producing an audit row.

### Running the Migration

```bash
psql -U postgres -d safemerchant -f migrations/002_metrics_schema.sql
```
