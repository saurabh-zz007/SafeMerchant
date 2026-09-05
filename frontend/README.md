# SafeMerchant Frontend — Autonomous AI Risk Manager

> Real-time operator dashboard and dispute review interface built with Flutter.  
> Built for the Razorpay Buildathon (Track 2).

For full system architecture, sequence flows, and relational schemas, refer to:
- **[Full System Architecture & Flow](https://drive.google.com/file/d/1ejqt-4eVz13VRtZeBPR4Z0wa2-JjCo5Z/view?usp=sharing)**
- **[Backend Architecture Deep-Dive](https://drive.google.com/file/d/1WYrjE-iE4mFtOzSrwoQBndK_t89-MoAU/view?usp=sharing)**

---

## ⚡ Local vs. Live Cloud Server Switch

The frontend includes a real-time environment switch allowing you to evaluate the complete system **with zero local backend setup**, or connect to your own local backend:

- **Local Server (Dev)**: `http://localhost:8000` (REST) | `ws://localhost:8000/ws/dashboard` (WebSocket)
- **Cloud Server (Staging)**: `https://safemerchant.onrender.com` (REST) | `wss://safemerchant.onrender.com/ws/dashboard` (WebSocket)

### How to Switch Servers in the UI

1. Launch the frontend dashboard.
2. In the navigation sidebar, click on **Developer Options** (terminal icon).
3. Enter the access passkey: **`admin`**.
4. Scroll to the **Backend Environment** card.
5. Select either:
   - **Local Server (Dev)**
   - **Cloud Server (Staging)**
6. The dashboard instantly reconnects the WebSocket stream (`/ws/dashboard`), updates the API base URL, and refreshes the dispute list and financial metrics without requiring an app restart.

> [!NOTE]
> **Evaluation Mode Notice:**  
> The **Developer Options** suite (environment switcher, synthetic scenario builder, and database reset) is provided specifically for testing and judge evaluation. It is gated behind the `admin` passkey and will be automatically removed/disabled once the platform moves out of evaluation mode into production.

---

## 🛠️ Testing Disputes Directly via UI

You do not need to run terminal commands to test the system. You can synthesize and dispatch complete dispute workflows directly inside the UI:

1. Open **Developer Options** (Passkey: `admin`).
2. In the **Synthetic Scenario Builder**, select a preset scenario or customize the parameters:
   - Transaction Amount (INR)
   - Reason code (`fraudulent`, `chargeback`, `product_unacceptable`, etc.)
   - 2FA authentication state
   - Delivery tracking status & customer communication chat log
   - Account age and customer risk factors
3. Click **Dispatch Test Dispute**.
4. The system immediately creates operational merchant records, calculates the HMAC-SHA256 signature, dispatches the webhook into the active server (local or cloud), and redirects you to the live dispute investigation stream.

*(If you prefer testing via terminal, refer to the [Backend README](../backend/README.md) for Windows PowerShell and cURL scripts with the configured secret `whsec_8kQ2vN9xZmR7pL4tY6bJ3cF1dK5wA0hE`).*

---

## 🚀 Getting Started

### Prerequisites

- [Flutter SDK](https://flutter.dev/docs/get-started/install) (3.24+ recommended)
- Google Chrome (for Web) or Visual Studio C++ build tools (for Windows Desktop)

### 1. Install Dependencies

From the `frontend/` directory:

```powershell
flutter pub get
```

### 2. Run on Windows Desktop

```powershell
flutter run -d windows
```

*(If the Windows platform folder is missing on a fresh clone, run `flutter create . --platforms=windows` first).*

### 3. Run on Web (Chrome)

```powershell
flutter run -d chrome
```

### 4. Custom Backend Addresses (Optional)

If your local backend runs on a custom IP or port, pass compile-time environment flags:

```powershell
flutter run -d windows --dart-define=LOCAL_SERVER_URL=localhost:8000 --dart-define=CLOUD_SERVER_URL=safemerchant.onrender.com
```

---

## 📱 Core Dashboard Features

1. **Live Dispute Stream (`/ws/dashboard`)**:
   - Real-time agent status updates as nodes in the LangGraph pipeline execute (Ingestion, Validation, Evidence Synthesis, Risk Scoring, Razorpay Submission).
2. **Interactive Evidence Inspector**:
   - View generated evidence packages, AI defense rationale, and open secure signed Supabase PDF links directly in the browser.
3. **Human-in-the-Loop Review Queue**:
   - Review low-confidence or high-value disputes flagged for manual oversight. Operators can inspect defense confidence, edit rationale, and approve or reject submissions.
4. **Financial Metrics & Breakdown**:
   - Real-time metrics tracking dispute recovery rate, preserved capital, and reason-code distributions.
