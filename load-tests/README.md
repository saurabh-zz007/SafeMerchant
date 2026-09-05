# SafeMerchant Load Testing Suite (Locust Web UI)

Locust-based performance, end-to-end webhook ingestion, and gate-decision coverage testing suite for the **SafeMerchant Dispute Risk Agent** pipeline. Built using a **Feature-First Architecture** to test gate decisions, sequential pipelines, concurrent load, and held-out benchmark evaluation.

> 📊 **Evaluation & Metrics Report**:  
> For the complete 50-case audit report computed from live PostgreSQL runs against held-out ground truth, see **[Dispute Pipeline Evaluation & Metrics Report](../metrics_report.md)**.

---

## 🏗️ Feature-First Architecture

```
load-tests/
├── locustfile.py                              # Main Locust entry point (exports User classes)
├── testcase.json                             # Active dispute test cases executed by Locust (50 cases)
├── requirements.txt                          # Python dependencies (locust, python-dotenv, requests)
├── ground_truth.csv                          # 50-case ground-truth labels (SHOULD_WIN, SHOULD_LOSE, SHOULD_REFUND)
├── config/                                   # Configuration & environment variables
│   ├── __init__.py
│   └── settings.py                           # Target host, webhook secret, 10s delay pacing
├── core/                                     # Shared core utilities & protocols
│   ├── __init__.py
│   ├── security.py                           # HMAC-SHA256 signature generator for Razorpay
│   └── webhook_client.py                     # Signed webhook client wrapper for Locust
├── Held Out Sets/                            # Held-out benchmark raw test cases & SQL seed files
│   ├── SeedDatasheetSQLformat.txt            # SQL DDL/DML to insert merchant evidence rows for all 50 cases
│   ├── test1-10.text                         # Held-out dispute webhook payloads (ORD_2006 to ORD_2015)
│   ├── test10-20.text                        # Held-out dispute webhook payloads (ORD_2016 to ORD_2025)
│   └── test20-50.txt                         # Held-out dispute webhook payloads (ORD_2101 to ORD_2130)
└── features/                                 # Feature-specific modules
    └── dispute_webhook/                      # Dispute Webhook Ingestion Feature
        ├── __init__.py
        ├── models/
        │   ├── __init__.py
        │   └── payload_models.py             # Scenario dataclasses and metadata
        ├── data/
        │   ├── __init__.py
        │   └── test_payloads.py              # Dynamic testcase.json loader & fallback scenarios
        ├── tasks.py                          # Sequential & random TaskSets driven by testcase.json
        └── user.py                           # Locust HttpUser classes
```

---

## 📋 Dynamic `testcase.json` Execution

Locust dynamically loads and fires the dispute payloads configured in **[`load-tests/testcase.json`](testcase.json)**:

- **Fully Dynamic & Pre-Loaded**: Contains the complete set of **50 evaluation test cases** (`ORD_2006`–`ORD_2025` and `ORD_2101`–`ORD_2130`), covering a wide distribution of reason codes (`fraudulent`, `product_not_received`, `goods_not_as_described`, `credit_not_processed`), amounts (₹499 to ₹89,999), and customer legitimacy signals.
- **Hot-Reloading**: Changes to `testcase.json` are automatically detected via file modification timestamp (`mtime`), so you can add, remove, or modify cases without restarting Locust.
- **Granular Reporting in Web UI**: Each test case is tracked individually in the Locust Web UI metrics table by order ID, reason code, and amount (e.g. `1_ORD_2006_product_not_received_INR_2499`).
- **10-Second Delay Pacing**: Each request waits 10 seconds (`TASK_DELAY_SECONDS=10.0`) between executions, allowing the backend LangGraph agent and ReportLab PDF workers to complete async processing without rate limit exhaustion.

---

## 📦 Held Out Sets & Re-running with Locust

The raw source files used to generate the system evaluation metrics reside in the **[`Held Out Sets/`](Held%20Out%20Sets/)** folder:

| File | Order ID Range | Description |
|---|---|---|
| **`Held Out Sets/SeedDatasheetSQLformat.txt`** | All 50 Orders | SQL script inserting `orders`, `shipping_logs`, `customer_communications`, and `risk_signals` into the database. Evidence tables **must** be populated prior to firing webhooks. |
| **`Held Out Sets/test1-10.text`** | `ORD_2006` – `ORD_2015` | 10 fraudulent / friendly-fraud scenarios. |
| **`Held Out Sets/test10-20.text`** | `ORD_2016` – `ORD_2025` | 10 merchant-liability / legitimate customer refund scenarios. |
| **`Held Out Sets/test20-50.txt`** | `ORD_2101` – `ORD_2130` | 30 diverse edge cases (high-value electronics, missing OTP, damaged deliveries, courier exceptions). |

All 50 dispute payloads from these held-out files are compiled directly into **[`testcase.json`](testcase.json)**.

### How to Re-Run the 50 Benchmark Cases

1. **Seed Merchant Evidence into Database** (if running fresh):
   ```bash
   psql -U <user> -d <database> -f "load-tests/Held Out Sets/SeedDatasheetSQLformat.txt"
   ```

2. **Ensure Backend is Running**:
   ```bash
   cd backend
   python run.py
   ```

3. **Start the Locust Web UI**:
   ```bash
   cd load-tests
   locust -f locustfile.py --host http://localhost:8000
   ```

4. **Trigger the Run in Locust**:
   - Open **http://localhost:8089**
   - Set **Number of users**: `1`
   - Set **Ramp-up rate**: `1`
   - Set **User class**: `DisputeSequentialUser`
   - Click **Start swarming**. Locust will iterate through all 50 cases in `testcase.json` sequentially with a 10-second pause between requests.

5. **Generate Fresh Metrics Report**:
   Once all disputes have been processed by the agent pipeline, regenerate the metrics document:
   ```bash
   python backend/evaluation/generate_metrics_report.py --output metrics_report.md
   ```

---

## 📊 Pipeline Evaluation Metrics (50-Case Held-Out Test)

The latest results pulled from live PostgreSQL after executing all 50 cases in `testcase.json` via Locust are documented in **[metrics_report.md](../metrics_report.md)**:

| Metric | Result | Calculation / Meaning |
|---|---|---|
| **Accuracy** | **76.00%** (38/50) | `(TP + TN) / Total` |
| **Precision** | **68.97%** (20/29) | `TP / (TP + FP)` — Reliability of Contest decisions |
| **Recall** | **86.96%** (20/23) | `TP / (TP + FN)` — Capture rate of winnable disputes |
| **Confusion Matrix** | **TP: 20 \| FN: 3 \| FP: 9 \| TN: 18** | Complete classification matrix |
| **Total False Positive Cost** | **₹179,795** | Sum of dispute amounts + ₹500 fee for wrongly contested cases |

See the full breakdown, per-dispute audit table, and false positive / negative root-cause analysis in **[metrics_report.md](../metrics_report.md)**.

---

## ⚙️ Configuration & Environment Variables

Configure options via `load-tests/.env` or backend environment:

| Variable | Default | Description |
|---|---|---|
| `TARGET_HOST` | `http://localhost:8000` | Backend base URL |
| `WEBHOOK_PATH` | `/api/v1/webhook` | Webhook endpoint path |
| `RAZORPAY_WEBHOOK_SECRET` | `whsec_8kQ2vN9xZmR7pL4tY6bJ3cF1dK5wA0hE` | Secret used for HMAC-SHA256 signature header |
| `TASK_DELAY_SECONDS` | `10.0` | Delay between consecutive test executions |
| `UNIQUE_DISPUTE_IDS` | `false` | `false` preserves canonical dispute IDs (`disp_test_*`) for idempotency testing; `true` appends random suffixes for continuous stress testing |
