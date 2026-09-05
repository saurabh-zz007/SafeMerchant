# SafeMerchant Backend — Autonomous AI Risk Manager

> Defense-only agentic system for automated chargeback dispute resolution.  
> Built for the Razorpay Buildathon (Track 2).

For full system architecture, sequence flows, and relational schemas, refer to:
- **[Full System Architecture & Flow](https://drive.google.com/file/d/1ejqt-4eVz13VRtZeBPR4Z0wa2-JjCo5Z/view?usp=sharing)**
- **[Backend Architecture Deep-Dive](https://drive.google.com/file/d/1WYrjE-iE4mFtOzSrwoQBndK_t89-MoAU/view?usp=sharing)**

---

## ⚡ Local vs. Live Cloud Server

The SafeMerchant backend can be run locally or accessed via the hosted live cloud server:

- **Local Server**: `http://localhost:8000` (REST) | `ws://localhost:8000/ws/dashboard` (WebSocket)
- **Live Cloud Server**: `https://safemerchant.onrender.com` (REST) | `wss://safemerchant.onrender.com/ws/dashboard` (WebSocket)

> [!TIP]
> **Zero Local Setup Needed for Testing:**  
> If you only want to explore the Flutter dashboard and run test disputes, you do not need to set up Python or PostgreSQL locally. Run the frontend, open **Developer Options** (Passkey: `admin`), and toggle the environment switch to **Cloud Server**.

---

## Quick Start (Local Backend)

### 1. Prerequisites

- Python 3.11+
- PostgreSQL 14+ (local instance or cloud database such as Supabase)

### 2. Virtual Environment & Dependencies

```bash
# Create virtual environment
python -m venv .venv

# Activate environment
# On Windows (PowerShell):
.\.venv\Scripts\Activate.ps1
# On macOS/Linux:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Environment Variables

Create `.env` in `backend/`:

```env
# ── Database Connection ──
DATABASE_URL=postgresql+asyncpg://<user>:<password>@<host>:<port>/<dbname>

# ── LLM Provider (OpenRouter) ──
OPENROUTER_API_KEY=your_openrouter_api_key
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_MODEL_NAME=openai/gpt-4o

# ── Razorpay API Credentials ──
RAZORPAY_KEY_ID=your_razorpay_key_id
RAZORPAY_KEY_SECRET=your_razorpay_key_secret
RAZORPAY_WEBHOOK_SECRET=whsec_8kQ2vN9xZmR7pL4tY6bJ3cF1dK5wA0hE

# ── Agent Gate Thresholds ──
AUTO_SUBMIT_SCORE_THRESHOLD=0.85
AUTO_SUBMIT_AMOUNT_CEILING_INR=10000
AUTO_REFUND_AMOUNT_CEILING_INR=10000

# ── Supabase Storage (Evidence PDFs) ──
SUPABASE_URL=https://<project-ref>.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your_supabase_service_role_key
SUPABASE_STORAGE_BUCKET=evidence-pdfs
MAX_CONCURRENT_EVIDENCE_JOBS=5

# ── Server ──
HOST=0.0.0.0
PORT=8000
DEBUG=true
```

### 4. Database Setup & Seed Data

```bash
# 1. Run Alembic migrations to create the schema and checkpoint tables
alembic upgrade head

# 2. Insert canonical test scenario orders (ORD_2001 to ORD_2005)
psql -U postgres -d safemerchant -f SeedDatasheetSQLformat.txt
```

### 5. Run the Server

Start the backend using `run.py` (which configures the Windows `SelectorEventLoop` for psycopg async compatibility):

```bash
python run.py
```

*(Or via Uvicorn directly: `uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload`)*

> [!NOTE]
> The background `EvidenceWorkerPool` and `PeriodicBreakdownWorker` start automatically inside FastAPI's async lifespan. No separate Celery or Redis worker process is required.

---

## Triggering & Testing Dispute Webhooks

The backend strictly verifies Razorpay's HMAC-SHA256 signature on `POST /api/v1/webhook`.  
**Configured Test Secret**: `whsec_8kQ2vN9xZmR7pL4tY6bJ3cF1dK5wA0hE`

You can test disputes through any of the following methods:

### Method 1: Directly via Frontend UI (Developer Options)
The easiest way to generate a dispute without writing curl scripts:
1. Open the Flutter dashboard and navigate to **Developer Options** in the sidebar.
2. Enter passkey: **`admin`**.
3. Use the **Synthetic Scenario Builder** to set amount, delivery status, customer chat transcripts, 2FA, and reason code.
4. Click **Dispatch Test Dispute**. The backend creates operational records, signs the HMAC webhook internally, and dispatches it into the live pipeline.

---

### Method 2: Windows PowerShell Script
Run the following script in Windows PowerShell to compute the HMAC-SHA256 signature and post a valid webhook:

```powershell
$secret = "whsec_8kQ2vN9xZmR7pL4tY6bJ3cF1dK5wA0hE"
$targetUrl = "http://localhost:8000/api/v1/webhook"

$body = @"
{
  "entity": "event",
  "account_id": "acc_CFvOKjkTwf3GQy",
  "event": "payment.dispute.created",
  "contains": ["payment", "dispute"],
  "payload": {
    "payment": {
      "entity": {
        "id": "pay_XYZ2003",
        "entity": "payment",
        "amount": 349900,
        "currency": "INR",
        "status": "captured",
        "order_id": "ORD_2003",
        "email": "friendly_fraud1@outlook.com",
        "contact": "+919876543210",
        "method": "card"
      }
    },
    "dispute": {
      "entity": {
        "id": "disp_test_$(Get-Random)",
        "entity": "dispute",
        "payment_id": "pay_XYZ2003",
        "amount": 349900,
        "currency": "INR",
        "amount_deducted": 0,
        "reason_code": "fraudulent",
        "status": "open",
        "phase": "chargeback"
      }
    }
  }
}
"@

# Compute HMAC-SHA256 Signature
$hmac = [System.Security.Cryptography.HMACSHA256]::new([System.Text.Encoding]::UTF8.GetBytes($secret))
$sigBytes = $hmac.ComputeHash([System.Text.Encoding]::UTF8.GetBytes($body))
$signature = -join ($sigBytes | ForEach-Object { "{0:x2}" -f $_ })

# Send Webhook
$response = Invoke-RestMethod -Method Post -Uri $targetUrl -Headers @{
    "Content-Type" = "application/json"
    "X-Razorpay-Signature" = $signature
} -Body $body

$response | ConvertTo-Json
```

*(To target the cloud server, change `$targetUrl = "https://safemerchant.onrender.com/api/v1/webhook"`).*

---

### Method 3: Linux / macOS cURL Command

```bash
SECRET="whsec_8kQ2vN9xZmR7pL4tY6bJ3cF1dK5wA0hE"
TARGET_URL="http://localhost:8000/api/v1/webhook"
DISPUTE_ID="disp_test_$RANDOM"

BODY=$(cat <<EOF
{
  "entity": "event",
  "account_id": "acc_CFvOKjkTwf3GQy",
  "event": "payment.dispute.created",
  "contains": ["payment", "dispute"],
  "payload": {
    "payment": {
      "entity": {
        "id": "pay_XYZ2003",
        "entity": "payment",
        "amount": 349900,
        "currency": "INR",
        "status": "captured",
        "order_id": "ORD_2003",
        "email": "friendly_fraud1@outlook.com",
        "contact": "+919876543210",
        "method": "card"
      }
    },
    "dispute": {
      "entity": {
        "id": "${DISPUTE_ID}",
        "entity": "dispute",
        "payment_id": "pay_XYZ2003",
        "amount": 349900,
        "currency": "INR",
        "amount_deducted": 0,
        "reason_code": "fraudulent",
        "status": "open",
        "phase": "chargeback"
      }
    }
  }
}
EOF
)

# Compute HMAC signature using openssl
SIGNATURE=$(echo -n "$BODY" | openssl dgst -sha256 -hmac "$SECRET" | sed 's/^.* //')

curl -X POST "$TARGET_URL" \
  -H "Content-Type: application/json" \
  -H "X-Razorpay-Signature: $SIGNATURE" \
  -d "$BODY"
```

---

### Method 4: Dev Endpoint (Automated Seeding + Internal Signing)
You can call the development endpoint directly to insert matching merchant database rows and dispatch a signed webhook in a single HTTP call:

```bash
curl -X POST http://localhost:8000/api/v1/dev/create-test-dispute \
  -H "Content-Type: application/json" \
  -d '{
    "amount_inr": 3499,
    "item_description": "Nike Running Shoes - Size 9",
    "delivery_status": "Delivered",
    "customer_communication": "Received shoes yesterday, perfect fit.",
    "is_2fa_verified": true,
    "account_age_days": 180,
    "reason_code": "chargeback"
  }'
```

---

## Core API Endpoints

| Method | Path | Description |
| :--- | :--- | :--- |
| `POST` | `/api/v1/webhook` | Ingests Razorpay webhook, validates HMAC, returns HTTP 202 |
| `GET` | `/api/v1/disputes` | Lists historical disputes with review context |
| `GET` | `/api/v1/disputes/{id}` | Gets dispute details, evidence status, and audit history |
| `POST` | `/api/v1/disputes/{id}/review` | Submits operator review decision (`accept`/`reject`) |
| `POST` | `/api/v1/disputes/{id}/retry-evidence` | Retries failed evidence generation job |
| `GET` | `/api/v1/disputes/{id}/evidence-url` | Returns 1-hour signed Supabase CDN URL for evidence PDF |
| `PATCH` | `/api/v1/disputes/{id}` | Manual field update with transactional audit log entry |
| `GET` | `/api/v1/disputes/{id}/audit` | Fetches complete audit trail for a dispute |
| `GET` | `/api/v1/metrics/summary` | Aggregated financial metrics for date range |
| `GET` | `/api/v1/metrics/breakdown` | Current breakdown by reason_code, outcome, or phase |
| `GET` | `/api/v1/metrics/repeat-patterns` | Flags repeated customer emails across disputes |
| `POST` | `/api/v1/dev/create-test-dispute` | Constructs synthetic records and dispatches signed webhook |
| `DELETE` | `/api/v1/admin/reset` | Clears all dispute tables and purges Supabase storage bucket |
| `GET` | `/api/v1/health` | Backend health probe |
| `WS` | `/ws/dashboard` | Real-time WebSocket connection for live agent updates |
