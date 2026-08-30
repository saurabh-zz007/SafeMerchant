-- ============================================================
-- SafeMerchant — Metrics Schema Migration
-- Run against: PostgreSQL 14+
-- Adds: dispute_events, dispute_audit_log, dispute_metrics_daily,
--        dispute_breakdowns, and new columns on disputes.
-- ============================================================

-- ──────────────────────────────────────────────────────────────
-- 1. ALTER disputes — add metrics-relevant columns
-- ──────────────────────────────────────────────────────────────

-- The existing disputes table only stores id, status, created_at,
-- updated_at, and history (JSONB).  We promote the fields needed
-- for queryable metrics into real columns.

ALTER TABLE disputes
    ADD COLUMN IF NOT EXISTS amount_paise          INT,
    ADD COLUMN IF NOT EXISTS reason_code           VARCHAR(50),
    ADD COLUMN IF NOT EXISTS customer_email        VARCHAR(100),
    ADD COLUMN IF NOT EXISTS payment_id            VARCHAR(50),
    ADD COLUMN IF NOT EXISTS order_id              VARCHAR(50),
    ADD COLUMN IF NOT EXISTS phase                 VARCHAR(50)   DEFAULT 'chargeback',
    ADD COLUMN IF NOT EXISTS outcome               VARCHAR(50)   DEFAULT 'open',
    ADD COLUMN IF NOT EXISTS updated_by            VARCHAR(100)  DEFAULT 'system',
    ADD COLUMN IF NOT EXISTS webhook_received_at   TIMESTAMP WITH TIME ZONE,
    ADD COLUMN IF NOT EXISTS resolved_at           TIMESTAMP WITH TIME ZONE;

-- Index for repeat-customer / repeat-email pattern queries
CREATE INDEX IF NOT EXISTS idx_disputes_customer_email
    ON disputes (customer_email);

-- Index for reason_code breakdown queries
CREATE INDEX IF NOT EXISTS idx_disputes_reason_code
    ON disputes (reason_code);

-- Index for outcome-based filtering
CREATE INDEX IF NOT EXISTS idx_disputes_outcome
    ON disputes (outcome);


-- ──────────────────────────────────────────────────────────────
-- 2. dispute_events — append-only immutable raw event log
-- ──────────────────────────────────────────────────────────────
-- Every webhook payload and significant system event gets a row
-- here verbatim.  This is the source of truth for replay/backfill.
-- NEVER update or delete rows in this table.

CREATE TABLE IF NOT EXISTS dispute_events (
    id              BIGSERIAL       PRIMARY KEY,
    dispute_id      VARCHAR(100)    NOT NULL,
    event_type      VARCHAR(50)     NOT NULL,
    payload         JSONB           NOT NULL,
    occurred_at     TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_dispute_events_dispute_occurred
    ON dispute_events (dispute_id, occurred_at);

-- Trigger: prevent any UPDATE or DELETE on dispute_events
CREATE OR REPLACE FUNCTION prevent_dispute_events_mutation()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'dispute_events is append-only: % operations are forbidden', TG_OP;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_dispute_events_no_update ON dispute_events;
CREATE TRIGGER trg_dispute_events_no_update
    BEFORE UPDATE ON dispute_events
    FOR EACH ROW
    EXECUTE FUNCTION prevent_dispute_events_mutation();

DROP TRIGGER IF EXISTS trg_dispute_events_no_delete ON dispute_events;
CREATE TRIGGER trg_dispute_events_no_delete
    BEFORE DELETE ON dispute_events
    FOR EACH ROW
    EXECUTE FUNCTION prevent_dispute_events_mutation();


-- ──────────────────────────────────────────────────────────────
-- 3. dispute_audit_log — append-only log of manual edits
-- ──────────────────────────────────────────────────────────────
-- Any edit to a disputes row from a human-initiated endpoint
-- MUST write to this table in the SAME transaction.

CREATE TABLE IF NOT EXISTS dispute_audit_log (
    id              BIGSERIAL       PRIMARY KEY,
    dispute_id      VARCHAR(100)    NOT NULL REFERENCES disputes(id),
    field           VARCHAR(100)    NOT NULL,
    old_value       TEXT,
    new_value       TEXT,
    changed_by      VARCHAR(100)    NOT NULL DEFAULT 'user',
    changed_at      TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    note            TEXT
);

CREATE INDEX IF NOT EXISTS idx_dispute_audit_log_dispute_changed
    ON dispute_audit_log (dispute_id, changed_at);


-- ──────────────────────────────────────────────────────────────
-- 4. dispute_metrics_daily — pre-aggregated daily metrics
-- ──────────────────────────────────────────────────────────────
-- One row per calendar day.  Trend charts read from this table.
-- NEVER compute trends by scanning disputes live.

CREATE TABLE IF NOT EXISTS dispute_metrics_daily (
    date                    DATE        PRIMARY KEY,
    total_disputes          INT         NOT NULL DEFAULT 0,
    won                     INT         NOT NULL DEFAULT 0,
    lost                    INT         NOT NULL DEFAULT 0,
    action_required         INT         NOT NULL DEFAULT 0,
    amount_won_paise        BIGINT      NOT NULL DEFAULT 0,
    amount_lost_paise       BIGINT      NOT NULL DEFAULT 0,
    amount_at_risk_paise    BIGINT      NOT NULL DEFAULT 0,
    avg_response_seconds    INT,
    sla_breached            INT         NOT NULL DEFAULT 0
);


-- ──────────────────────────────────────────────────────────────
-- 5. dispute_breakdowns — aggregation table (materialized view equiv.)
-- ──────────────────────────────────────────────────────────────
-- Current-state breakdowns that don't need daily granularity.
-- Refreshed after event ingestion, NOT on every page load.

CREATE TABLE IF NOT EXISTS dispute_breakdowns (
    id                  SERIAL          PRIMARY KEY,
    dimension           VARCHAR(50)     NOT NULL,
    dimension_value     VARCHAR(100)    NOT NULL,
    count               INT             NOT NULL DEFAULT 0,
    amount_paise        BIGINT          NOT NULL DEFAULT 0,
    refreshed_at        TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_dispute_breakdowns_dim
    ON dispute_breakdowns (dimension, dimension_value);
