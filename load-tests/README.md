# SafeMerchant Load Testing Suite (Locust Web UI)

Locust-based performance and gate-decision coverage testing suite for the **SafeMerchant Dispute Risk Agent** webhook ingestion pipeline. Built using a **Feature-First Architecture** to test gate decisions, sequential pipelines, and concurrent load.

---

## 🏗️ Feature-First Architecture

```
load-tests/
├── locustfile.py                              # Main Locust entry point (exports User classes)
├── requirements.txt                          # Python dependencies (locust, python-dotenv, requests)
├── config/                                   # Configuration & environment variables
│   ├── __init__.py
│   └── settings.py                           # Target host, webhook secret, 10s delay pacing
├── core/                                     # Shared core utilities & protocols
│   ├── __init__.py
│   ├── security.py                           # HMAC-SHA256 signature generator for Razorpay
│   └── webhook_client.py                     # Signed webhook client wrapper for Locust
└── features/                                 # Feature-specific modules
    └── dispute_webhook/                      # Dispute Webhook Ingestion Feature
        ├── __init__.py
        ├── models/
        │   ├── __init__.py
        │   └── payload_models.py             # Scenario dataclasses and metadata
        ├── data/
        │   ├── __init__.py
        │   └── test_payloads.py              # The 5 Gate-Decision test payloads (ORD_2001 - ORD_2005)
        ├── tasks.py                          # Sequential & random TaskSets with 10s delay
        └── user.py                           # Locust HttpUser classes
```

---

## 📦 The 5 Gate-Decision Coverage Scenarios

Each scenario below routes through a specific gate decision in the SafeMerchant LangGraph agent based on merchant evidence in PostgreSQL:

| # | Gate Decision | Order ID | Dispute ID | Amount | DB Evidence & Logic |
|---|---|---|---|---|---|
| **1** | **`auto_refund`** | `ORD_2001` | `disp_2001` | ₹2,999 | Genuinely lost in transit (Delhivery unfulfilled, customer notified support early), low value ($\le$ ₹5,000) $\to$ **Auto Refund** |
| **2** | **`refund_review`** | `ORD_2002` | `disp_2002` | ₹24,999 | Genuinely lost in transit (BlueDart unfulfilled), high value (> ₹5,000) $\to$ **Refund Review (HITL approval)** |
| **3** | **`auto_submit`** | `ORD_2003` | `disp_2003` | ₹3,499 | Strong winnable defense (OTP delivered + customer chat confirms fit), low value $\to$ **Auto Submit (Contest)** |
| **4** | **`human_review`** | `ORD_2004` | `disp_2004` | ₹18,500 | Ambiguous evidence (Left at door without signature, no chat on file, high value) $\to$ **Human Review (HITL Contest)** |
| **5** | **`accept_loss`** | `ORD_2005` | `disp_2005` | ₹1,299 | Weak defense, vague chat, high risk telemetry (account age 1 day, no 2FA) $\to$ **Accept Loss** |

---

## 🚀 Running the Tests via Locust Web UI

1. Start your backend server:
   ```bash
   cd backend
   uvicorn app.main:app --reload --port 8000
   ```

2. Start the Locust test engine:
   ```bash
   cd load-tests
   locust -f locustfile.py --host http://localhost:8000
   ```

3. Open **http://localhost:8089** in your browser:
   - **Number of users**: Enter `1` (for sequential test) or `5`–`10` (for concurrent load)
   - **Ramp-up rate**: `1`
   - **Host**: `http://localhost:8000`
   - **User class**: 
     - Choose `DisputeSequentialUser` to run the 5 gate-decision scenarios sequentially with a 10s delay between each.
     - Choose `DisputeWebhookUser` for randomized concurrent load testing with a 10s pacing per user.

---

## ⚙️ Configuration & Environment Variables

You can configure options in `backend/.env` or create `load-tests/.env`:

| Variable | Default | Description |
|---|---|---|
| `TARGET_HOST` | `http://localhost:8000` | Backend base URL |
| `WEBHOOK_PATH` | `/api/v1/webhook` | Webhook endpoint path |
| `RAZORPAY_WEBHOOK_SECRET` | `whsec_8kQ2vN9xZmR7pL4tY6bJ3cF1dK5wA0hE` | Secret used for HMAC-SHA256 signature header |
| `TASK_DELAY_SECONDS` | `10.0` | Delay between consecutive test executions |
| `UNIQUE_DISPUTE_IDS` | `false` | `false` sends the canonical dispute IDs (`disp_2001` - `disp_2005`) for idempotency testing; `true` appends random suffixes for continuous stress testing |
