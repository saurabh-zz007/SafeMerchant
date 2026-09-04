import asyncio
import hashlib
import hmac
import json
import logging
import statistics
import sys
import time
import uuid

from httpx import ASGITransport, AsyncClient
from app.core.config import settings
from app.main import app, lifespan

# Silence engine logging so output is clean
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

def build_payload(dispute_id: str, order_id: str, payment_id: str, amount_paise: int = 299900) -> dict:
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
                    "amount": amount_paise,
                    "currency": "INR",
                    "base_amount": amount_paise,
                    "status": "captured",
                    "order_id": order_id,
                    "email": f"user_{dispute_id}@example.com",
                    "contact": "+919900000000",
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
                    "amount": amount_paise,
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

async def send_single(client: AsyncClient, payload: dict, secret: str) -> dict:
    payload_bytes = json.dumps(payload).encode("utf-8")
    sig = sign_payload(payload_bytes, secret)
    t0 = time.perf_counter()
    try:
        resp = await client.post(
            "/api/v1/webhook",
            content=payload_bytes,
            headers={
                "Content-Type": "application/json",
                "X-Razorpay-Signature": sig,
            },
            timeout=30.0,
        )
        latency_ms = (time.perf_counter() - t0) * 1000
        return {
            "status_code": resp.status_code,
            "latency_ms": latency_ms,
            "data": resp.json() if resp.status_code in (200, 202) else resp.text,
        }
    except Exception as e:
        latency_ms = (time.perf_counter() - t0) * 1000
        return {
            "status_code": 599,
            "latency_ms": latency_ms,
            "error": str(e),
        }

async def run_benchmark(concurrency: int = 10, total_requests: int = 20):
    print("\n" + "="*80, flush=True)
    print(f">> STARTING CONCURRENT WEBHOOK BENCHMARK ({total_requests} requests, concurrency={concurrency})", flush=True)
    print("="*80 + "\n", flush=True)

    async with lifespan(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. Warm-up
            print(">> Pre-warming connection pool...", flush=True)
            await client.get("/api/v1/health")

            # 2. Prepare Distinct New Disputes
            test_disputes = []
            for i in range(total_requests):
                d_id = f"disp_bench_{uuid.uuid4().hex[:8]}"
                p_id = f"pay_bench_{uuid.uuid4().hex[:8]}"
                o_id = "ORD_2001"
                test_disputes.append(build_payload(d_id, o_id, p_id))

            print(f">> Blasting {total_requests} distinct new dispute webhooks...", flush=True)
            sem = asyncio.Semaphore(concurrency)

            async def bounded_call(p):
                async with sem:
                    return await send_single(client, p, settings.razorpay_webhook_secret)

            t_batch_start = time.perf_counter()
            results = await asyncio.gather(*[bounded_call(p) for p in test_disputes], return_exceptions=True)
            total_batch_duration = (time.perf_counter() - t_batch_start) * 1000

            valid_results = [r for r in results if isinstance(r, dict)]
            latencies = [r["latency_ms"] for r in valid_results if r.get("status_code") in (200, 202)]
            status_codes = [r["status_code"] for r in valid_results]

            mean_lat = statistics.mean(latencies) if latencies else 0.0
            median_lat = statistics.median(latencies) if latencies else 0.0
            min_lat = min(latencies) if latencies else 0.0
            max_lat = max(latencies) if latencies else 0.0
            stdev_lat = statistics.stdev(latencies) if len(latencies) > 1 else 0.0

            print("\n" + "="*80, flush=True)
            print("BENCHMARK RESULTS - CONCURRENT INGESTION (LOCK CONTENTION TEST)", flush=True)
            print("="*80, flush=True)
            print(f"Total Requests:       {total_requests}", flush=True)
            print(f"Success Count (202):  {status_codes.count(202)}", flush=True)
            print(f"Total Batch Time:     {total_batch_duration:.2f} ms", flush=True)
            if total_batch_duration > 0:
                print(f"Throughput:           {total_requests / (total_batch_duration / 1000):.2f} req/sec", flush=True)
            print("-" * 80, flush=True)
            print(f"Min Latency:          {min_lat:.2f} ms", flush=True)
            print(f"Mean Latency:         {mean_lat:.2f} ms", flush=True)
            print(f"Median (p50):         {median_lat:.2f} ms", flush=True)
            print(f"Max Latency:          {max_lat:.2f} ms", flush=True)
            print(f"Standard Deviation:   {stdev_lat:.2f} ms (Variance: {stdev_lat**2:.2f})", flush=True)
            if mean_lat > 0:
                print(f"Max-to-Mean Ratio:    {max_lat / mean_lat:.2f}x", flush=True)
            print("="*80 + "\n", flush=True)

            # 3. Test Duplicate Idempotency Wave
            print(">> Blasting exact same disputes again to verify duplicate idempotency guard...", flush=True)
            t_dup_start = time.perf_counter()
            dup_results = await asyncio.gather(*[bounded_call(p) for p in test_disputes], return_exceptions=True)
            total_dup_duration = (time.perf_counter() - t_dup_start) * 1000
            valid_dup = [r for r in dup_results if isinstance(r, dict)]
            dup_latencies = [r["latency_ms"] for r in valid_dup]
            dup_status_codes = [r["status_code"] for r in valid_dup]

            print("\n" + "="*80, flush=True)
            print("IDEMPOTENCY / RETRY BENCHMARK RESULTS", flush=True)
            print("="*80, flush=True)
            print(f"Total Duplicate Requests: {total_requests}", flush=True)
            print(f"200 OK / 202 Accepted:    {dup_status_codes.count(200)} / {dup_status_codes.count(202)}", flush=True)
            if dup_latencies:
                print(f"Mean Duplicate Latency:   {statistics.mean(dup_latencies):.2f} ms", flush=True)
                print(f"Max Duplicate Latency:    {max(dup_latencies):.2f} ms", flush=True)
            print("="*80 + "\n", flush=True)

            # Allow background tasks to settle
            await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(run_benchmark(concurrency=10, total_requests=20))

