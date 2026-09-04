import asyncio
import hashlib
import hmac
import json
import logging
import sys
import time
import uuid

from httpx import ASGITransport, AsyncClient
from app.core.config import settings
from app.main import app, lifespan

# Ensure UTF-8 stdout
sys.stdout.reconfigure(encoding='utf-8')

# Ensure app logger is INFO level
logging.getLogger("app.dispute.routes").setLevel(logging.INFO)
logging.getLogger("app.dispute.service").setLevel(logging.INFO)

def generate_dispute_payload(dispute_id: str, order_id: str, payment_id: str):
    now_ts = int(time.time())
    return {
        "entity": "event",
        "account_id": "acc_CFvOKjkTwf3GQy",
        "event": "payment.dispute.created",
        "contains": ["payment", "dispute"],
        "payload": {
            "payment": {
                "entity": {
                    "id": payment_id,
                    "entity": "payment",
                    "amount": 299900,
                    "currency": "INR",
                    "base_amount": 299900,
                    "status": "captured",
                    "order_id": order_id,
                    "email": "customer.test@example.com",
                    "contact": "+919876543210",
                    "method": "card",
                    "amount_refunded": 0,
                    "created_at": now_ts - 86400,
                }
            },
            "dispute": {
                "entity": {
                    "id": dispute_id,
                    "entity": "dispute",
                    "payment_id": payment_id,
                    "amount": 299900,
                    "currency": "INR",
                    "amount_deducted": 0,
                    "reason_code": "fraudulent",
                    "respond_by": now_ts + 86400 * 5,
                    "status": "open",
                    "phase": "chargeback",
                    "created_at": now_ts,
                }
            },
        },
        "created_at": now_ts,
    }

def sign_payload(payload_bytes: bytes, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()

async def main():
    dispute_id = f"disp_trace_{uuid.uuid4().hex[:8]}"
    order_id = "ORD_2001" # Standard test order in DB
    payment_id = f"pay_{uuid.uuid4().hex[:10]}"

    payload = generate_dispute_payload(dispute_id, order_id, payment_id)
    payload_bytes = json.dumps(payload).encode("utf-8")
    sig = sign_payload(payload_bytes, settings.razorpay_webhook_secret)

    print("\n" + "="*80)
    print(f">> INITIATING SINGLE WEBHOOK REQUEST TRACE: {dispute_id}")
    print("="*80 + "\n")

    # Run inside app lifespan so graph & DB pools are initialized
    async with lifespan(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. Warm connection pool with a DB query
            print(">> Pre-warming DB connection pool with active query...")
            from app.core.db import async_session_factory
            from sqlalchemy import text
            async with async_session_factory() as session:
                await session.execute(text("SELECT 1"))
            print(">> DB connection pool warmed and dialect initialized.\n")
            
            # 2. Execute target single webhook request (NEW dispute: is_new_insert = True)
            print(">> [REQUEST 1: GENUINELY NEW DISPUTE]")
            t0 = time.perf_counter()
            response = await client.post(
                "/api/v1/webhook",
                content=payload_bytes,
                headers={
                    "Content-Type": "application/json",
                    "X-Razorpay-Signature": sig,
                },
            )
            client_roundtrip_ms = (time.perf_counter() - t0) * 1000

            print("\n" + "="*80)
            print(f">> CLIENT HTTP RESPONSE RECEIVED (REQUEST 1)")
            print(f"Status Code: {response.status_code}")
            print(f"Response JSON: {json.dumps(response.json(), indent=2)}")
            print(f"Client-Observed Roundtrip: {client_roundtrip_ms:.2f}ms")
            print("="*80 + "\n")

            # Allow background tasks to spin slightly
            await asyncio.sleep(1)

            # 3. Execute duplicate webhook request (DUPLICATE retry: is_new_insert = False)
            print(">> [REQUEST 2: DUPLICATE / RETRY WEBHOOK FOR SAME DISPUTE ID]")
            t1 = time.perf_counter()
            response2 = await client.post(
                "/api/v1/webhook",
                content=payload_bytes,
                headers={
                    "Content-Type": "application/json",
                    "X-Razorpay-Signature": sig,
                },
            )
            client_roundtrip_ms2 = (time.perf_counter() - t1) * 1000

            print("\n" + "="*80)
            print(f">> CLIENT HTTP RESPONSE RECEIVED (REQUEST 2 - DUPLICATE)")
            print(f"Status Code: {response2.status_code}")
            print(f"Response JSON: {json.dumps(response2.json(), indent=2)}")
            print(f"Client-Observed Roundtrip: {client_roundtrip_ms2:.2f}ms")
            print("="*80 + "\n")

            await asyncio.sleep(2)

if __name__ == "__main__":
    asyncio.run(main())
