-- ============================================================
-- SafeMerchant — Initial Database Schema + Seed Data
-- Run against: PostgreSQL 14+
-- ============================================================

-- 1. Core Orders Ledger
CREATE TABLE IF NOT EXISTS orders (
    order_id VARCHAR(50) PRIMARY KEY,
    payment_id VARCHAR(50) UNIQUE NOT NULL,
    customer_email VARCHAR(100) NOT NULL,
    amount_inr INT NOT NULL,
    item_description TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 2. Physical Logistics & Delivery Logs
CREATE TABLE IF NOT EXISTS shipping_logs (
    tracking_id VARCHAR(50) PRIMARY KEY,
    order_id VARCHAR(50) NOT NULL REFERENCES orders(order_id) ON DELETE CASCADE,
    courier_partner VARCHAR(50) NOT NULL,
    delivery_status VARCHAR(50) NOT NULL,
    signed_by VARCHAR(100),
    delivery_timestamp TIMESTAMP WITH TIME ZONE
);

-- 3. Customer Interaction Transcripts
CREATE TABLE IF NOT EXISTS customer_communications (
    ticket_id VARCHAR(50) PRIMARY KEY,
    order_id VARCHAR(50) NOT NULL REFERENCES orders(order_id) ON DELETE CASCADE,
    channel VARCHAR(20) NOT NULL,
    message_transcript TEXT NOT NULL,
    logged_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 4. Authentication & Network Telemetry
CREATE TABLE IF NOT EXISTS risk_signals (
    signal_id SERIAL PRIMARY KEY,
    order_id VARCHAR(50) NOT NULL REFERENCES orders(order_id) ON DELETE CASCADE,
    ip_address VARCHAR(50) NOT NULL,
    device_fingerprint VARCHAR(100) NOT NULL,
    is_2fa_verified BOOLEAN NOT NULL DEFAULT FALSE,
    account_age_days INT NOT NULL DEFAULT 0
);


-- ============================================================
-- SEED DATA — 3 dispute archetypes
-- ============================================================

-- Orders
INSERT INTO orders (order_id, payment_id, customer_email, amount_inr, item_description, created_at)
VALUES
    ('ORD_1001', 'pay_XYZ1001', 'scammer1@gmail.com', 52976, 'Sony WH-1000XM5 Headphones', '2026-08-10T14:00:00Z'),
    ('ORD_1002', 'pay_XYZ1002', 'hacked_account@yahoo.com', 15000, 'Annual Software Subscription', '2026-08-15T09:30:00Z'),
    ('ORD_1003', 'pay_XYZ1003', 'angry_buyer@outlook.com', 4500, 'Cotton T-Shirt - Blue', '2026-08-18T11:15:00Z')
ON CONFLICT (order_id) DO NOTHING;

-- Shipping Logs
INSERT INTO shipping_logs (tracking_id, order_id, courier_partner, delivery_status, signed_by, delivery_timestamp)
VALUES
    ('TRK_DEL_999', 'ORD_1001', 'Delhivery', 'Delivered', 'Self (OTP Verified)', '2026-08-13T16:45:00Z'),
    ('TRK_BDP_888', 'ORD_1003', 'BlueDart', 'In_Transit', NULL, NULL)
ON CONFLICT (tracking_id) DO NOTHING;

-- Customer Communications
INSERT INTO customer_communications (ticket_id, order_id, channel, message_transcript, logged_at)
VALUES
    ('TCK_551', 'ORD_1001', 'Email', 'Customer: How do I pair these headphones to my Mac? Support: Press the power button for 5 seconds.', '2026-08-14T10:00:00Z'),
    ('TCK_552', 'ORD_1003', 'WhatsApp', 'Customer: I wore the shirt but I dont like the color anymore. Can I return it? Support: Sorry, worn items cannot be returned.', '2026-08-19T12:00:00Z')
ON CONFLICT (ticket_id) DO NOTHING;

-- Risk Signals
INSERT INTO risk_signals (order_id, ip_address, device_fingerprint, is_2fa_verified, account_age_days)
VALUES
    ('ORD_1002', '49.36.2.11 (Mumbai)', 'iPhone 14 Pro - Safari', TRUE, 450)
ON CONFLICT DO NOTHING;
