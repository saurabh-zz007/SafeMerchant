> For a comprehensive system architecture, sequence flows, and relational schemas, please refer to the [SafeMerchant Full System Architecture & Flow](https://drive.google.com/file/d/1ejqt-4eVz13VRtZeBPR4Z0wa2-JjCo5Z/view?usp=sharing) and the [Backend Architecture Deep-Dive](https://drive.google.com/file/d/1WYrjE-iE4mFtOzSrwoQBndK_t89-MoAU/view?usp=sharing).

---

# SafeMerchant — Developer Getting Started Guide

**Autonomous Risk & Chargeback Defense Platform for Razorpay Merchants**  
*Razorpay Buildathon (Track 2)*

SafeMerchant is an autonomous, defense-only agentic risk management platform designed to automate chargeback triage and evidence generation for digital merchants on Razorpay. It links merchant business data (orders, logistics logs, support transcripts, and risk telemetry) with Razorpay APIs, providing an operations dashboard built in Flutter alongside a stateful, asynchronous Python backend (FastAPI + LangGraph + PostgreSQL).

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

- **Python 3.11+**
- **Flutter SDK 3.x+** (with Windows desktop support enabled: `flutter config --enable-windows-desktop`)
- **PostgreSQL 14+** (running locally or through a managed service such as Supabase)
- **Git**

---

## 3. Backend Setup Guide

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

*(Alternatively, you can install the package in editable mode via pip: `pip install -e .`)*

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
RAZORPAY_WEBHOOK_SECRET=

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

---

### 3.3 Database Setup, Migrations & Seed Data

1. **Create the PostgreSQL Database** (if using a local instance):
   ```bash
   psql -U postgres -c "CREATE DATABASE safemerchant;"
   ```

2. **Run Alembic Migrations**:
   Apply all migration versions to construct the 12-table relational schema and checkpoint tables:
   ```bash
   alembic upgrade head
   ```

3. **Insert Seed Data**:
   The repository includes test scenarios (orders `ORD_2001` through `ORD_2005` covering all gate decisions) located in `backend/SeedDatasheetSQLformat.txt`. Load them into your database:
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
cd ../frontend
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

### 4.3 Connecting to a Custom Backend

By default, the dashboard connects to `http://localhost:8000` (REST) and `ws://localhost:8000/ws/dashboard` (WebSockets). To point the frontend to another backend, pass `--dart-define` parameters:

```bash
flutter run -d windows --dart-define=LOCAL_SERVER_URL=localhost:8000
```

---

## 5. Testing & Verification Workflows

### 5.1 Automated Backend Tests

From the `backend/` directory, run the automated test suite:

```bash
pytest
```

The automated test suite verifies:
- **Idempotency**: Single-statement atomic upsert (`xmax = 0`) and duplicate webhook suppression.
- **Webhook Ingestion**: HMAC-SHA256 signature verification and payload validation.
- **Evidence Compilation**: In-memory ReportLab PDF rendering for delivery proofs, chat transcripts, and activity logs.
- **Submission Flow**: Razorpay Documents API upload and sandbox limitation classification (`contest_expected_failure`).
- **Worker Queue**: Concurrency throttling (`asyncio.Semaphore`) and row-locking (`FOR UPDATE SKIP LOCKED`).

### 5.2 Synthetic Dispute Generation & Testing

You can simulate disputes and test the agentic pipeline in two ways:

1. **Using the Frontend Developer Options Screen:**
   - In the Flutter dashboard sidebar, open **Developer Options** (enter default PIN `1234` when prompted).
   - Use the **Synthetic Scenario Builder** to configure amount, reason code, delivery status, 2FA, and chat transcripts.
   - Click **Dispatch Test Dispute**. The backend creates operational records, signs an HMAC webhook, and feeds it into `/api/v1/webhook`.
2. **Using the Reset Utility:**
   - Use the **Reset Database** button in Developer Options (or send `DELETE /api/v1/admin/reset`) to wipe test disputes and purge the Supabase storage bucket.

---

## 6. Architecture & Deep-Dive References

For comprehensive architectural blueprints, sequence flows, decision matrices, and relational schemas, refer to the following documents:

- **[SafeMerchant Full System Architecture & Flow (Frontend + Backend + Cloud)](https://drive.google.com/file/d/1ejqt-4eVz13VRtZeBPR4Z0wa2-JjCo5Z/view?usp=sharing)**: Complete system overview covering the Flutter operations UI, real-time WebSocket protocol, ReportLab evidence generation, and end-to-end sequence flows.
- **[Backend Architecture & Flow Deep-Dive](https://drive.google.com/file/d/1WYrjE-iE4mFtOzSrwoQBndK_t89-MoAU/view?usp=sharing)**: Backend deep-dive covering the LangGraph state machine, Super Steps 1–3, deterministic grounding verification, and the 12-table relational database schema.
- **[backend/app/dispute/agent/graph.py](backend/app/dispute/agent/graph.py)**: LangGraph state machine definition and node wiring.
