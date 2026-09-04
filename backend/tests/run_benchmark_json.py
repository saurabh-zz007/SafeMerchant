import asyncio
import hashlib
import hmac
import json
import logging
import statistics
import time
import uuid

from httpx import ASGITransport, AsyncClient
from app.core.config import settings
from app.main import app, lifespan

logging.getLogger("app.dispute.routes").setLevel(logging.INFO)

def build_payload(dispute_id: str, order_id: str, payment_id: str):
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
                    "email": f"user_{dispute_id}@example.com",
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

async def send_single(client, payload, secret):
    body_bytes = json.dumps(payload).encode("utf-8")
    sig = hmac.new(secret.encode("utf-8"), body_bytes, hashlib.sha256).hexdigest()
    t0 = time.perf_counter()
    resp = await client.post(
        "/api/v1/webhook",
        content=body_bytes,
        headers={"Content-Type": "application/json", "X-Razorpay-Signature": sig},
    )
    lat = (time.perf_counter() - t0) * 1000
    return {"status_code": resp.status_code, "latency_ms": lat, "data": resp.json()}

async def run_suite():
    async with lifespan(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            from app.core.db import async_session_factory
            from sqlalchemy import text
            async with async_session_factory() as session:
                await session.execute(text("SELECT 1"))

            total_requests = 20
            concurrency = 10
            test_disputes = [
                build_payload(f"disp_bench_{uuid.uuid4().hex[:8]}", "ORD_2001", f"pay_bench_{uuid.uuid4().hex[:8]}")
                for _ in range(total_requests)
            ]

            sem = asyncio.Semaphore(concurrency)
            async def bounded(p):
                async with sem:
                    return await send_single(client, p, settings.razorpay_webhook_secret)

            t0 = time.perf_counter()
            results = await asyncio.gather(*[bounded(p) for p in test_disputes])
            total_duration = (time.perf_counter() - t0) * 1000

            lats = [r["latency_ms"] for r in results]
            sorted_lats = sorted(lats)
            stats = {
                "total_requests": len(results),
                "success_202": sum(1 for r in results if r["status_code"] == 202),
                "batch_duration_ms": round(total_duration, 2),
                "throughput_req_sec": round(len(results) / (total_duration / 1000), 2),
                "min_ms": round(min(lats), 2),
                "max_ms": round(max(lats), 2),
                "mean_ms": round(statistics.mean(lats), 2),
                "median_ms": round(statistics.median(lats), 2),
                "stdev_ms": round(statistics.stdev(lats), 2),
                "p90_ms": round(sorted_lats[int(len(sorted_lats)*0.9)], 2),
                "p95_ms": round(sorted_lats[int(len(sorted_lats)*0.95)], 2),
                "max_to_mean_ratio": round(max(lats) / statistics.mean(lats), 2),
            }

            with open("benchmark_results.json", "w") as f:
                json.dump(stats, f, indent=2)

            print(json.dumps(stats, indent=2), flush=True)
            await asyncio.sleep(2)

if __name__ == "__main__":
    asyncio.run(run_suite())
