> For a comprehensive system architecture, sequence flows, and relational schemas, please refer to the [SafeMerchant Full System Architecture & Flow](https://drive.google.com/file/d/1ejqt-4eVz13VRtZeBPR4Z0wa2-JjCo5Z/view?usp=sharing) and the [Backend Architecture Deep-Dive](https://drive.google.com/file/d/1WYrjE-iE4mFtOzSrwoQBndK_t89-MoAU/view?usp=sharing).

---

# SafeMerchant — Developer Getting Started Guide

**Autonomous Risk & Chargeback Defense Platform for Razorpay Merchants**  
*Razorpay Buildathon (Track 2)*

SafeMerchant is an autonomous, defense-only agentic risk management platform designed to automate chargeback triage and evidence generation for digital merchants on Razorpay. It links merchant business data (orders, logistics logs, support transcripts, and risk telemetry) with Razorpay APIs, providing an operations dashboard built in Flutter alongside a stateful, asynchronous Python backend (FastAPI + LangGraph + PostgreSQL).

---

## ⚡ Fast-Track: Live Cloud Backend Available

> **Don't want to set up Python, PostgreSQL, and environment variables locally?**  
> A live backend instance is currently deployed and running in the cloud at **`https://safemerchant.onrender.com`**.  
> You can skip the backend setup entirely, run **only the Flutter frontend**, open **Developer Options** in the app (default passkey: `admin`), and toggle the environment switch to **Cloud Server**. The dashboard will immediately stream live disputes and WebSocket events from the hosted cloud backend.

---

## 1. Repository Structure

```
SafeMerchant/
├── backend/                  # FastAPI + LangGraph backend service
│   ├── app/                  # Application code
│   │   ├── core/             # Configuration, async DB session, checkpointer, Supabase storage
│   │   ├── dispute/          # Routes, ORM models, repos, LangGraph agent nodes, worker pool
│   │   ├── proof_renderer/   # ReportLab in-memory PDF compilation engine & schemas
│   │   └── main.py           # FastAPI app factory, lifespan & worker pool initialization
│   ├── migrations/           # Database migrations (Alembic versions & SQL baseline DDL)
│   ├── evaluation/           # Evaluation runner, metrics, and synthetic dispute generator
│   ├── tests/                # Unit, integration, and load benchmark tests
│   ├── alembic.ini           # Alembic database migration configuration
│   ├── pyproject.toml        # Build system & package dependency specifications
│   ├── requirements.txt      # Pinned Python package dependencies
│   ├── run.py                # Server launcher script (configures Windows loop policy & uvicorn)
│   └── SeedDatasheetSQLformat.txt # SQL seed data for canonical dispute test scenarios
├── frontend/                 # Flutter desktop & web operations dashboard
│   ├── lib/
│   │   ├── models/           # Dispute, metrics, and dashboard event models
│   │   ├── services/         # REST client (DisputeApiService) & WebSocket client
│   │   ├── theme/            # Material 3 light and dark theme definitions
│   │   ├── utils/            # Status pill & label display mapping helpers
│   │   ├── view_models/      # GetX state controller (DashboardController)
│   │   └── views/            # Dashboard screens (Overview, Disputes, Analytics, Settings, Dev)
│   └── pubspec.yaml          # Flutter dependencies (get, syncfusion_flutter_pdfviewer)
└── load-tests/               # Locust load test suite for webhook stress testing
```

---

## 2. Prerequisites

Ensure you have the following installed on your development machine:

- **Python 3.11+** *(only if running backend locally)*
- **Flutter SDK 3.x+** (with Windows desktop support enabled: `flutter config --enable-windows-desktop`)
- **PostgreSQL 14+** *(only if running backend locally; local instance or managed Supabase)*
- **Git**

---

## 3. Backend Setup Guide (Local Server)

*(If you are connecting the frontend to the live Cloud Server, you can skip to [Section 4: Frontend Setup Guide](#4-frontend-setup-guide).)*

### 3.1 Virtual Environment & Dependencies

Navigate to the `backend/` directory:

```bash
cd backend
```

Create and activate a Python virtual environment:

**On Windows (PowerShell):**
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

**On macOS/Linux:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install the dependencies:

```bash
pip install -r requirements.txt
```

*(Alternatively: `pip install -e .`)*

---

### 3.2 Environment Variables Configuration

Create a `.env` file in the `backend/` directory:

**On Windows:**
```powershell
copy .env.example .env
```

**On macOS/Linux:**
```bash
cp .env.example .env
```

Populate the required environment variables in `backend/.env`:

```env
# ── PostgreSQL Database Connection ──
# Async SQLAlchemy connection string (postgresql+asyncpg://<user>:<password>@<host>:<port>/<dbname>)
DATABASE_URL=

# ── LLM Provider (OpenRouter) ──
OPENROUTER_API_KEY=
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_MODEL_NAME=openai/gpt-4o

# ── Razorpay API Credentials ──
RAZORPAY_KEY_ID=
RAZORPAY_KEY_SECRET=
RAZORPAY_WEBHOOK_SECRET=whsec_8kQ2vN9xZmR7pL4tY6bJ3cF1dK5wA0hE

# ── Agent Gate Thresholds ──
AUTO_SUBMIT_SCORE_THRESHOLD=0.85
AUTO_SUBMIT_AMOUNT_CEILING_INR=10000
AUTO_REFUND_AMOUNT_CEILING_INR=10000

# ── Supabase Storage (Private Evidence PDFs) ──
SUPABASE_URL=
SUPABASE_SERVICE_ROLE_KEY=
SUPABASE_STORAGE_BUCKET=evidence-pdfs

# ── Evidence Worker Queue ──
MAX_CONCURRENT_EVIDENCE_JOBS=5

# ── Server Host & Port ──
HOST=0.0.0.0
PORT=8000
DEBUG=true
```

> [!IMPORTANT]
> **Razorpay Webhook Secret:**  
> The test webhook secret configured across the project and test suites is:  
> `RAZORPAY_WEBHOOK_SECRET=whsec_8kQ2vN9xZmR7pL4tY6bJ3cF1dK5wA0hE`  
> All incoming webhooks must be signed with HMAC-SHA256 using this secret, otherwise the backend rejects them with `HTTP 400 Invalid webhook signature`.

---

### 3.3 Database Setup, Migrations & Seed Data

1. **Create the PostgreSQL Database** (if using a local instance):
   ```bash
   psql -U postgres -c "CREATE DATABASE safemerchant;"
   ```

2. **Run Alembic Migrations**:
   Construct the 12-table relational schema and checkpoint tables:
   ```bash
   alembic upgrade head
   ```

3. **Insert Seed Data**:
   Load the test scenarios (orders `ORD_2001` through `ORD_2005` covering all gate decisions) located in `backend/SeedDatasheetSQLformat.txt`:
   ```bash
   psql -U postgres -d safemerchant -f SeedDatasheetSQLformat.txt
   ```

---

### 3.4 Starting the Backend Server & Worker Pool

SafeMerchant runs background queue processing (`EvidenceWorkerPool`) and periodic OLAP aggregation (`PeriodicBreakdownWorker`) directly inside FastAPI's asynchronous application lifespan. There is no need to launch a separate Celery or Redis worker process.

Start the server using either method:

**Method 1 — Using the run script (recommended for Windows SelectorEventLoop compatibility):**
```bash
python run.py
```

**Method 2 — Using Uvicorn directly:**
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Upon startup, the server initializes:
- Supabase Storage bucket verification (`evidence-pdfs`)
- The concurrency-capped `EvidenceWorkerPool`
- The decoupled 30-second `PeriodicBreakdownWorker`
- The `AsyncPostgresSaver` LangGraph checkpointer

**Verify Backend Health:**
- API Probe: `http://localhost:8000/api/v1/health`
- Interactive OpenAPI Docs: `http://localhost:8000/docs`

---

## 4. Frontend Setup Guide

### 4.1 Prerequisites & Dependencies

Navigate to the `frontend/` directory:

```bash
cd frontend
```

Ensure platform support files exist:

```bash
flutter create . --platforms=windows
```

Install Flutter packages:

```bash
flutter pub get
```

> [!NOTE]
> **Code Generation:** This project does not use `build_runner` or code generators. Running `flutter pub get` is sufficient.

---

### 4.2 Running the Application

Launch the desktop client targeting Windows:

```bash
flutter run -d windows
```

*(Alternatively, to run as a web client in Google Chrome: `flutter run -d chrome`)*

---

### 4.3 Connecting to Cloud vs. Local Server

By default, the dashboard connects to the local backend at `http://localhost:8000` (REST) and `ws://localhost:8000/ws/dashboard` (WebSockets). 

You can switch to the live Cloud Server (`https://safemerchant.onrender.com`) at any time using:
1. **The In-App Developer Options Screen**: Toggle the environment switch inside the app UI without restarting.
2. **Command-Line Flag**: Pass `--dart-define` parameters during launch:
   ```bash
   flutter run -d windows --dart-define=LOCAL_SERVER_URL=localhost:8000
   ```

---

## 5. Developer Options Screen (In-App Testing Suite)

The Flutter frontend includes a built-in **Developer Options** screen accessible from the navigation sidebar.

> [!WARNING]
> **Testing Mode Notice:**  
> The Developer Options screen is an internal test-bench interface created specifically for reviewers, judges, and developers during the evaluation and hackathon phase. **It will be completely removed/disabled as soon as the application transitions out of testing mode into production.**

### Accessing Developer Options
1. In the Flutter dashboard sidebar, click **Developer Options**.
2. A security gatekeeper dialog will prompt for a passkey. Enter the default evaluation passkey: **`admin`**.

### Capabilities Provided in Developer Options:
1. **Live Environment Switcher**:
   - Easily toggle between **Local Server** (`http://localhost:8000`) and the hosted **Cloud Server** (`https://safemerchant.onrender.com`).
   - Switching environments immediately reconnects the WebSocket stream and reloads the disputes list and analytics.
2. **Synthetic Dispute Scenario Builder**:
   - Construct custom dispute test scenarios directly from the UI without writing curl commands or calculating HMAC signatures.
   - Configure: Amount (INR), Item Description, Courier Delivery Status (e.g. *Delivered*, *Signed*, *In Transit*, *Lost*), Customer Communication Transcripts, 2FA Verification Status, Account Age, and Dispute Reason Code.
   - Clicking **"Dispatch Test Dispute"** instructs the backend to seed the corresponding merchant database records (`orders`, `shipping_logs`, `customer_communications`, `risk_signals`), sign a valid Razorpay webhook payload with HMAC-SHA256, and post it to `/api/v1/webhook`.
3. **Database & Storage Reset Utility**:
   - Clicking **"Reset Database"** issues `DELETE /api/v1/admin/reset`.
   - Truncates all transactional tables in PostgreSQL (`disputes`, `dispute_events`, `dispute_audit_log`, `dispute_metrics_daily`, `dispute_breakdowns`, `checkpoints`), purges evidence PDFs from Supabase Storage, and broadcasts a `database_reset` WebSocket event so all connected dashboard screens instantly clear.

---

## 6. Testing & Dispute Simulation Workflows

Dispute test scenarios can be triggered directly through the UI (recommended) or via signed command-line scripts.

### 6.1 Dispatching Disputes via Frontend UI (Recommended)

1. Open the Flutter dashboard and navigate to **Developer Options** in the sidebar.
2. Enter passkey: **`admin`**.
3. Use the **Synthetic Scenario Builder** to configure transaction amount, delivery status, customer chat transcripts, 2FA, and dispute reason code.
4. Click **Dispatch Test Dispute**. The backend automatically seeds operational database records, generates a valid HMAC-SHA256 signature, and injects the webhook into the processing pipeline.

---

### 6.2 Manual Webhook Dispatching (PowerShell & cURL)

The webhook endpoint (`POST /api/v1/webhook`) strictly enforces Razorpay's HMAC-SHA256 signature authentication. Any request lacking a valid `X-Razorpay-Signature` computed using `RAZORPAY_WEBHOOK_SECRET` will be rejected with HTTP 400.

**Test Secret**:  
```text
whsec_8kQ2vN9xZmR7pL4tY6bJ3cF1dK5wA0hE
```

#### Option A: Windows PowerShell Script
Run the following script in Windows PowerShell to compute the HMAC-SHA256 signature and post a dispute webhook to your local server:

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

# Send HTTP Request
$response = Invoke-RestMethod -Method Post -Uri $targetUrl -Headers @{
    "Content-Type" = "application/json"
    "X-Razorpay-Signature" = $signature
} -Body $body

$response | ConvertTo-Json
```

*(To target the Cloud Server, change `$targetUrl = "https://safemerchant.onrender.com/api/v1/webhook"`).*

---

#### Option B: Linux / macOS cURL Command

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

#### Option C: Synthetic Scenario Endpoint (No Manual HMAC Computation Needed)
The backend exposes a development endpoint that automatically sets up database evidence records, signs the webhook internally, and dispatches it into the pipeline:

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

## 7. Architecture & Deep-Dive References

For comprehensive architectural blueprints, sequence flows, decision matrices, and relational schemas, refer to the following documents:

- **[SafeMerchant Full System Architecture & Flow (Frontend + Backend + Cloud)](https://drive.google.com/file/d/1ejqt-4eVz13VRtZeBPR4Z0wa2-JjCo5Z/view?usp=sharing)**: Complete system overview covering the Flutter operations UI, real-time WebSocket protocol, ReportLab evidence generation, and end-to-end sequence flows.
- **[Backend Architecture & Flow Deep-Dive](https://drive.google.com/file/d/1WYrjE-iE4mFtOzSrwoQBndK_t89-MoAU/view?usp=sharing)**: Backend deep-dive covering the LangGraph state machine, Super Steps 1–3, deterministic grounding verification, and the 12-table relational database schema.
- **[backend/app/dispute/agent/graph.py](backend/app/dispute/agent/graph.py)**: LangGraph state machine definition and node wiring.
