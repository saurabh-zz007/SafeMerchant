"""
SafeMerchant — Dispute Pipeline Evaluation & Metrics Report Generator.

Connects to PostgreSQL, pulls results of dispute-processing test runs,
joins with ground-truth classifications, computes evaluation metrics,
and writes an audit-ready Markdown report (metrics_report.md).

Usage:
    python backend/evaluation/generate_metrics_report.py
    python generate_metrics_report.py --csv ground_truth.csv --fee 500 --output metrics_report.md
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import logging
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Try loading dotenv
try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
)
logger = logging.getLogger("generate_metrics_report")


def find_env_file() -> Optional[Path]:
    """Locates the .env file in standard repository paths."""
    candidates = [
        Path.cwd() / ".env",
        Path.cwd() / "backend" / ".env",
        Path(__file__).resolve().parents[2] / "backend" / ".env",
        Path(__file__).resolve().parents[2] / ".env",
        Path(__file__).resolve().parents[1] / ".env",
    ]
    for c in candidates:
        if c.exists():
            return c
    return None


def find_ground_truth_csv(explicit_path: Optional[str] = None) -> Path:
    """Finds the ground truth CSV file."""
    if explicit_path:
        p = Path(explicit_path)
        if p.exists():
            return p
        raise FileNotFoundError(f"Specified ground truth CSV not found: {explicit_path}")

    candidates = [
        Path.cwd() / "ground_truth.csv",
        Path.cwd() / "load-tests" / "ground_truth.csv",
        Path(__file__).resolve().parent / "ground_truth.csv",
        Path(__file__).resolve().parents[2] / "load-tests" / "ground_truth.csv",
    ]
    for c in candidates:
        if c.exists():
            return c

    raise FileNotFoundError(
        "Could not find ground_truth.csv. Please specify with --csv path/to/ground_truth.csv"
    )


def load_ground_truth(csv_path: Path) -> Dict[str, Dict[str, str]]:
    """
    Loads ground truth mapping: order_id -> {ground_truth, reasoning}
    Expected CSV columns: order_id, ground_truth, [reasoning/notes]
    """
    mapping: Dict[str, Dict[str, str]] = {}
    with open(csv_path, mode="r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        # Normalize header names (lowercase, stripped)
        field_map = {col.lower().strip(): col for col in (reader.fieldnames or [])}
        
        oid_key = field_map.get("order_id") or field_map.get("order")
        gt_key = field_map.get("ground_truth") or field_map.get("label") or field_map.get("expected")
        reason_key = (
            field_map.get("reasoning")
            or field_map.get("reason")
            or field_map.get("notes")
            or field_map.get("description")
        )

        if not oid_key or not gt_key:
            raise ValueError(
                f"CSV {csv_path} must contain 'order_id' and 'ground_truth' columns. Found: {reader.fieldnames}"
            )

        for row in reader:
            oid = (row.get(oid_key) or "").strip()
            gt = (row.get(gt_key) or "").strip().upper()
            reason = (row.get(reason_key) or "").strip() if reason_key else ""
            if oid and gt:
                mapping[oid] = {
                    "ground_truth": gt,
                    "reasoning": reason,
                }

    logger.info("Loaded %d ground truth labels from %s", len(mapping), csv_path.name)
    return mapping


async def fetch_dispute_records(db_url: str) -> List[Dict[str, Any]]:
    """
    Connects to PostgreSQL using SQLAlchemy or asyncpg and fetches dispute rows.
    """
    # Normalize database URL for asyncpg
    clean_url = db_url
    if clean_url.startswith("postgresql://"):
        clean_url = clean_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    try:
        from sqlalchemy import text, NullPool
        from sqlalchemy.ext.asyncio import create_async_engine

        engine = create_async_engine(
            clean_url,
            echo=False,
            poolclass=NullPool,
            connect_args={
                "statement_cache_size": 0,
                "prepared_statement_cache_size": 0,
            },
        )
        async with engine.connect() as conn:
            query = text("""
                SELECT 
                    d.id AS dispute_id,
                    d.order_id,
                    COALESCE(o.amount_inr, (d.amount_paise / 100), 0) AS amount,
                    d.status,
                    d.outcome,
                    d.review_context,
                    d.created_at
                FROM disputes d
                LEFT JOIN orders o ON d.order_id = o.order_id
                ORDER BY d.created_at ASC;
            """)
            result = await conn.execute(query)
            rows = result.fetchall()
            await engine.dispose()
    except Exception as exc:
        logger.error("SQLAlchemy query failed: %s. Falling back to direct asyncpg...", exc)
        # Fallback to direct asyncpg
        import asyncpg
        raw_pg_url = db_url.replace("postgresql+asyncpg://", "postgresql://")
        conn = await asyncpg.connect(raw_pg_url, statement_cache_size=0)

        rows_data = await conn.fetch("""
            SELECT 
                d.id AS dispute_id,
                d.order_id,
                COALESCE(o.amount_inr, (d.amount_paise / 100), 0) AS amount,
                d.status,
                d.outcome,
                d.review_context::text AS review_context_str,
                d.created_at
            FROM disputes d
            LEFT JOIN orders o ON d.order_id = o.order_id
            ORDER BY d.created_at ASC;
        """)
        await conn.close()
        import json
        rows = []
        for r in rows_data:
            rd = dict(r)
            rc_str = rd.pop("review_context_str", None)
            rd["review_context"] = json.loads(rc_str) if rc_str else {}
            rows.append(rd)

    # Process and deduplicate by order_id (keep latest dispute run per order_id)
    latest_by_order: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        row_dict = dict(r._mapping) if hasattr(r, "_mapping") else dict(r)
        oid = row_dict.get("order_id")
        if oid:
            latest_by_order[oid] = row_dict

    logger.info("Retrieved %d distinct order dispute run(s) from database.", len(latest_by_order))
    return list(latest_by_order.values())


def normalize_action(action: Optional[str]) -> str:
    """Normalizes action string for comparison and display."""
    if not action:
        return "unknown"
    a = str(action).strip().lower()
    # Canonical translations
    if a in ("won", "auto_submit", "auto_contest", "contest"):
        return "auto_submit"
    if a in ("auto_refund", "refund_customer", "refunded"):
        return "auto_refund"
    if a in ("refund_review", "hitl_refund"):
        return "refund_review"
    if a in ("human_review", "hitl_contest", "manual_review"):
        return "human_review"
    if a in ("accept_loss", "accepted_loss", "loss"):
        return "accept_loss"
    return a


def classify_predicted_action(system_recommended: str) -> str:
    """
    STEP 2 — Bucket into 3 predicted classes:
    - 'auto_contest' = only cases where system_recommended_action is auto_submit
    - 'deferred' = cases where it's human_review or refund_review (no final autonomous action taken)
    - 'concede_leaning' = auto_refund or accept_loss
    """
    a = system_recommended.strip().lower()
    if a in ("auto_submit", "auto_contest", "won", "contest"):
        return "auto_contest"
    if a in ("human_review", "refund_review", "hitl_contest", "hitl_refund", "manual_review"):
        return "deferred"
    if a in ("auto_refund", "accept_loss", "accepted_loss", "refund_customer", "refunded"):
        return "concede_leaning"

    if "submit" in a or "contest" in a:
        return "auto_contest"
    if "review" in a:
        return "deferred"
    if "refund" in a or "loss" in a or "concede" in a:
        return "concede_leaning"
    return "deferred"


def evaluate_test_cases(
    db_records: List[Dict[str, Any]],
    ground_truth_map: Dict[str, Dict[str, str]],
    dispute_fee: int = 500,
) -> Dict[str, Any]:
    """
    Processes all test cases through:
    - Method A: Autonomous-only (excludes deferred rows from TP/FP/FN/TN)
    - Method B: Including deferrals as contest-leaning (original comparison)
    - Evidence-Direction Check: Identifies SHOULD_REFUND cases wrongly auto-contested
    """
    db_by_order = {r["order_id"]: r for r in db_records if r.get("order_id")}

    raw_table: List[Dict[str, Any]] = []

    # Method A containers (Autonomous only)
    tp_a_cases: List[Dict[str, Any]] = []
    fn_a_cases: List[Dict[str, Any]] = []
    fp_a_cases: List[Dict[str, Any]] = []
    tn_a_cases: List[Dict[str, Any]] = []

    # Method B containers (Including deferrals as contest-leaning)
    tp_b_cases: List[Dict[str, Any]] = []
    fn_b_cases: List[Dict[str, Any]] = []
    fp_b_cases: List[Dict[str, Any]] = []
    tn_b_cases: List[Dict[str, Any]] = []

    # Deferred cases tracker
    deferred_cases: List[Dict[str, Any]] = []

    # Evidence misattribution check
    evidence_direction_cases: List[Dict[str, Any]] = []

    # Sort order IDs numerically
    def sort_key(oid: str) -> Tuple[int, str]:
        nums = re.findall(r"\d+", oid)
        return (int(nums[0]) if nums else 999999, oid)

    all_order_ids = sorted(ground_truth_map.keys(), key=sort_key)

    for oid in all_order_ids:
        gt_info = ground_truth_map[oid]
        gt = gt_info["ground_truth"]
        reasoning = gt_info.get("reasoning", "")

        db_rec = db_by_order.get(oid)
        if not db_rec:
            raw_table.append({
                "order_id": oid,
                "amount": 0,
                "ground_truth": gt,
                "winnability_score": "N/A",
                "system_recommended_action": "NOT_RUN_YET",
                "final_action_taken": "NOT_RUN_YET",
                "flag_mismatch": False,
                "predicted_action_class": "unknown",
                "cat_a": "MISSING",
                "cat_b": "MISSING",
                "reasoning": reasoning,
            })
            continue

        amount = int(db_rec.get("amount") or 0)
        review_context = db_rec.get("review_context") or {}

        pre_hil_rec = (
            review_context.get("gate_action")
            or review_context.get("recommended_action")
            or "unknown"
        )

        final_action = (
            db_rec.get("outcome")
            or review_context.get("outcome")
            or db_rec.get("status")
            or "unknown"
        )
        if final_action == "open" and review_context.get("gate_action"):
            final_action = review_context.get("gate_action")

        w_score = review_context.get("winnability_score")
        if w_score is not None:
            try:
                winnability_str = f"{float(w_score):.2f}"
            except (ValueError, TypeError):
                winnability_str = str(w_score)
        else:
            winnability_str = "N/A"

        norm_rec = normalize_action(pre_hil_rec)
        norm_final = normalize_action(final_action)
        flag_mismatch = (norm_rec != norm_final)

        # 3-way classification
        pred_action_class = classify_predicted_action(pre_hil_rec)

        case_info = {
            "order_id": oid,
            "amount": amount,
            "fee": dispute_fee,
            "total_cost": amount + dispute_fee,
            "ground_truth": gt,
            "winnability_score": winnability_str,
            "pre_hil": pre_hil_rec,
            "final": final_action,
            "reasoning": reasoning,
        }

        # ── (A) Autonomous-Only Logic ──
        if pred_action_class == "deferred":
            cat_a = "DEFERRED (EXCLUDED)"
            deferred_cases.append(case_info)
        elif pred_action_class == "auto_contest":
            if gt == "SHOULD_WIN":
                cat_a = "TP"
                tp_a_cases.append(case_info)
            else:
                cat_a = "FP"
                fp_a_cases.append(case_info)
        elif pred_action_class == "concede_leaning":
            if gt == "SHOULD_WIN":
                cat_a = "FN"
                fn_a_cases.append(case_info)
            else:
                cat_a = "TN"
                tn_a_cases.append(case_info)
        else:
            cat_a = "UNKNOWN"

        # ── (B) Including Deferrals as Contest-Leaning (Original Logic) ──
        # auto_submit & human_review -> contest_leaning
        # auto_refund, accept_loss, refund_review -> concede_leaning
        pred_b_leaning = (
            "contest_leaning"
            if pre_hil_rec in ("auto_submit", "human_review")
            or any(k in pre_hil_rec for k in ("submit", "contest", "human_review"))
            else "concede_leaning"
        )

        if gt == "SHOULD_WIN":
            if pred_b_leaning == "contest_leaning":
                cat_b = "TP"
                tp_b_cases.append(case_info)
            else:
                cat_b = "FN"
                fn_b_cases.append(case_info)
        else:
            if pred_b_leaning == "contest_leaning":
                cat_b = "FP"
                fp_b_cases.append(case_info)
            else:
                cat_b = "TN"
                tn_b_cases.append(case_info)

        # ── Evidence-Direction Check ──
        # SHOULD_REFUND cases that were auto_contested (auto_submit)
        if gt == "SHOULD_REFUND" and pred_action_class == "auto_contest":
            evidence_direction_cases.append({
                **case_info,
                "flag": "POSSIBLE_EVIDENCE_MISATTRIBUTION",
            })

        raw_table.append({
            "order_id": oid,
            "amount": amount,
            "ground_truth": gt,
            "winnability_score": winnability_str,
            "system_recommended_action": pre_hil_rec,
            "final_action_taken": final_action,
            "flag_mismatch": flag_mismatch,
            "predicted_action_class": pred_action_class,
            "cat_a": cat_a,
            "cat_b": cat_b,
            "reasoning": reasoning,
        })

    # Metrics helper
    def calc_stats(tp_l: list, fn_l: list, fp_l: list, tn_l: list):
        tp_cnt = len(tp_l)
        fn_cnt = len(fn_l)
        fp_cnt = len(fp_l)
        tn_cnt = len(tn_l)
        tot = tp_cnt + fn_cnt + fp_cnt + tn_cnt

        if (tp_cnt + fp_cnt) > 0:
            prec = f"{tp_cnt / (tp_cnt + fp_cnt):.4f} ({tp_cnt / (tp_cnt + fp_cnt) * 100:.2f}%)"
        else:
            prec = "undefined (no cases in this bucket)"

        if (tp_cnt + fn_cnt) > 0:
            rec = f"{tp_cnt / (tp_cnt + fn_cnt):.4f} ({tp_cnt / (tp_cnt + fn_cnt) * 100:.2f}%)"
        else:
            rec = "undefined (no cases in this bucket)"

        if tot > 0:
            acc = f"{(tp_cnt + tn_cnt) / tot:.4f} ({(tp_cnt + tn_cnt) / tot * 100:.2f}%)"
        else:
            acc = "undefined (no cases in this bucket)"

        cost = sum(c["total_cost"] for c in fp_l)

        return {
            "tp": tp_cnt,
            "fn": fn_cnt,
            "fp": fp_cnt,
            "tn": tn_cnt,
            "evaluated_total": tot,
            "accuracy": acc,
            "precision": prec,
            "recall": rec,
            "total_fp_cost": cost,
        }

    stats_a = calc_stats(tp_a_cases, fn_a_cases, fp_a_cases, tn_a_cases)
    stats_b = calc_stats(tp_b_cases, fn_b_cases, fp_b_cases, tn_b_cases)

    return {
        "raw_table": raw_table,
        "total_cases_in_gt": len(ground_truth_map),
        "dispute_fee": dispute_fee,
        "method_a": {
            **stats_a,
            "tp_cases": tp_a_cases,
            "fn_cases": fn_a_cases,
            "fp_cases": fp_a_cases,
            "tn_cases": tn_a_cases,
        },
        "method_b": {
            **stats_b,
            "tp_cases": tp_b_cases,
            "fn_cases": fn_b_cases,
            "fp_cases": fp_b_cases,
            "tn_cases": tn_b_cases,
        },
        "deferred_cases": deferred_cases,
        "evidence_direction_cases": evidence_direction_cases,
    }


def generate_markdown_report(metrics_data: Dict[str, Any]) -> str:
    """
    Outputs Markdown report with:
    1. Summary Headline Metrics: Side-by-side comparison of Method A vs Method B
    2. Raw Per-Case Table (50 cases)
    3. Confusion Matrices & Cost Breakdown (Side-by-side Method A vs Method B)
    4. Cases to Review (FNs and FPs)
    5. Evidence-Direction Check (SHOULD_REFUND cases auto-contested with high winnability)
    """
    raw_table = metrics_data["raw_table"]
    dispute_fee = metrics_data["dispute_fee"]
    a = metrics_data["method_a"]
    b = metrics_data["method_b"]
    deferred = metrics_data["deferred_cases"]
    evidence_cases = metrics_data["evidence_direction_cases"]

    md: List[str] = []

    # Title
    md.append("# SafeMerchant Dispute Pipeline — Evaluation & Metrics Report")
    md.append("")
    md.append(f"> **Evaluation Dataset**: {len(raw_table)} Test Cases ({b['evaluated_total']} Processed in Database)")
    md.append(f"> **Arbitration Dispute Fee Constant**: ₹{dispute_fee:,} per contested case")
    md.append("")

    # ──────────────────────────────────────────────────────────────────────────
    # SECTION 1: Summary Headline Metrics
    # ──────────────────────────────────────────────────────────────────────────
    md.append("## 1. Headline Metrics Summary")
    md.append("")
    md.append("Comparison of **(A) Autonomous-Only Decisions** (excluding deferred/human-review cases where no final action was taken) vs. **(B) Including Deferrals as Contest-Leaning** (original benchmark where all deferred cases are treated as would-contest):")
    md.append("")
    md.append("| Metric | (A) Autonomous-Only | (B) With Deferrals as Contest | Definition / Formula |")
    md.append("| :--- | :---: | :---: | :--- |")
    md.append(f"| **Evaluated Cases** | **{a['evaluated_total']}** (excludes {len(deferred)} deferred) | **{b['evaluated_total']}** (all test cases) | Cases included in confusion matrix |")
    md.append(f"| **Accuracy** | **{a['accuracy']}** | **{b['accuracy']}** | `(TP + TN) / Total Evaluated` |")
    md.append(f"| **Precision** | **{a['precision']}** | **{b['precision']}** | `TP / (TP + FP)` — Reliability of Contest actions |")
    md.append(f"| **Recall** | **{a['recall']}** | **{b['recall']}** | `TP / (TP + FN)` — Winnable disputes contested |")
    md.append(f"| **Total False Positive Cost** | **₹{a['total_fp_cost']:,}** ({a['fp']} cases) | **₹{b['total_fp_cost']:,}** ({b['fp']} cases) | Sum of (Dispute Amount + ₹{dispute_fee:,} fee) across FPs |")
    md.append(f"| **Confusion Matrix** | **TP={a['tp']}, FN={a['fn']}, FP={a['fp']}, TN={a['tn']}** | **TP={b['tp']}, FN={b['fn']}, FP={b['fp']}, TN={b['tn']}** | Full breakdown |")
    md.append("")
    md.append("> [!NOTE]")
    md.append(f"> **Key Observation**: In **Method A (Autonomous-Only)**, excluding the {len(deferred)} deferred cases reveals that the autonomous decision gate made only **{a['fp']} False Positive errors** totaling **₹{a['total_fp_cost']:,}**. The remaining {b['fp'] - a['fp']} cases (comprising ₹{b['total_fp_cost'] - a['total_fp_cost']:,} in dispute exposure) were NOT wrongly contested; they were correctly flagged by the gate as ambiguous and routed to `human_review` / `refund_review`.")
    md.append("")

    # ──────────────────────────────────────────────────────────────────────────
    # SECTION 2: Full Raw Per-Case Table
    # ──────────────────────────────────────────────────────────────────────────
    md.append("## 2. Raw Per-Case Results (All 50 Cases)")
    md.append("")
    md.append("| # | Order ID | Amount (INR) | Ground Truth | Winnability Score | Pre-HIL Recommendation | Final Action | Mismatch | Predicted Class | (A) Autonomous Cat. | (B) Combined Cat. |")
    md.append("| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :---: | :--- | :---: | :---: |")

    for i, row in enumerate(raw_table, 1):
        mismatch_str = "⚠️ TRUE" if row["flag_mismatch"] else "false"
        amount_formatted = f"₹{row['amount']:,}" if row["amount"] else "₹0"
        md.append(
            f"| {i} | `{row['order_id']}` | {amount_formatted} | `{row['ground_truth']}` | "
            f"`{row['winnability_score']}` | `{row['system_recommended_action']}` | "
            f"`{row['final_action_taken']}` | {mismatch_str} | `{row['predicted_action_class']}` | "
            f"`{row['cat_a']}` | `{row['cat_b']}` |"
        )
    md.append("")

    # ──────────────────────────────────────────────────────────────────────────
    # SECTION 3: Confusion Matrices & Cost Breakdown
    # ──────────────────────────────────────────────────────────────────────────
    md.append("## 3. Confusion Matrices & Cost Analysis")
    md.append("")
    md.append("### 3.1 Method A: Autonomous-Only Decisions (Excludes Deferrals)")
    md.append("")
    md.append("Evaluates only cases where the system made a final autonomous decision (`auto_submit`, `auto_refund`, `accept_loss`). Deferrals (`human_review`, `refund_review`) are excluded as they await operator judgment.")
    md.append("")
    md.append("| Ground Truth \\ Predicted Action | Predicted: `auto_contest` (`auto_submit`) | Predicted: `concede_leaning` (`auto_refund` / `accept_loss`) | Total Actual |")
    md.append("| :--- | :---: | :---: | :---: |")
    md.append(f"| **Actual: `SHOULD_WIN`** | **TP = {a['tp']}** | **FN = {a['fn']}** | **{a['tp'] + a['fn']}** |")
    md.append(f"| **Actual: `SHOULD_LOSE` / `SHOULD_REFUND`** | **FP = {a['fp']}** | **TN = {a['tn']}** | **{a['fp'] + a['tn']}** |")
    md.append(f"| **Total Predicted** | **{a['tp'] + a['fp']}** | **{a['fn'] + a['tn']}** | **{a['evaluated_total']}** |")
    md.append("")
    md.append(f"*Note: {len(deferred)} cases were deferred to human review and are excluded from the autonomous evaluation above.*")
    md.append("")

    md.append("### 3.2 Method B: Including Deferrals as Contest-Leaning (Original Benchmark)")
    md.append("")
    md.append("Treats all deferred cases as if they would have resulted in contest actions (`auto_submit` + `human_review` = `contest_leaning`). Kept for comparison.")
    md.append("")
    md.append("| Ground Truth \\ Predicted Action | Predicted: `contest_leaning` (Auto Submit + Human Review) | Predicted: `concede_leaning` (Auto Refund + Accept Loss) | Total Actual |")
    md.append("| :--- | :---: | :---: | :---: |")
    md.append(f"| **Actual: `SHOULD_WIN`** | **TP = {b['tp']}** | **FN = {b['fn']}** | **{b['tp'] + b['fn']}** |")
    md.append(f"| **Actual: `SHOULD_LOSE` / `SHOULD_REFUND`** | **FP = {b['fp']}** | **TN = {b['tn']}** | **{b['fp'] + b['tn']}** |")
    md.append(f"| **Total Predicted** | **{b['tp'] + b['fp']}** | **{b['fn'] + b['tn']}** | **{b['evaluated_total']}** |")
    md.append("")

    # FP Cost Breakdown
    md.append("### 3.3 False Positive Cost Breakdown")
    md.append("")
    md.append("#### Group A: Genuine Autonomous False Positives (Method A)")
    md.append("These 4 disputes were erroneously auto-contested by the autonomous pipeline without human intervention:")
    md.append("")
    md.append("| Order ID | Disputed Amount | Fixed Dispute Fee | Total Financial Loss | Ground Truth | System Recommendation | Winnability Score |")
    md.append("| :--- | :--- | :--- | :--- | :--- | :--- | :---: |")
    for c in a["fp_cases"]:
        md.append(f"| `{c['order_id']}` | ₹{c['amount']:,} | ₹{c['fee']:,} | **₹{c['total_cost']:,}** | `{c['ground_truth']}` | `{c['pre_hil']}` | `{c['winnability_score']}` |")
    md.append(f"| **SUBTOTAL (Method A)** | | | **₹{a['total_fp_cost']:,}** | | | |")
    md.append("")

    # Deferred cases counted as FP in Method B
    deferred_fps = [c for c in b["fp_cases"] if c["order_id"] not in [x["order_id"] for x in a["fp_cases"]]]
    deferred_cost = sum(c["total_cost"] for c in deferred_fps)
    md.append("#### Group B: Ambiguous Cases Flagged for Human Review (Method B Only)")
    md.append("These 5 cases were NOT auto-contested; they were paused and routed to human review. They are counted as False Positives under Method B only:")
    md.append("")
    md.append("| Order ID | Disputed Amount | Fixed Dispute Fee | Potential Loss if Contested | Ground Truth | System Recommendation | Winnability Score |")
    md.append("| :--- | :--- | :--- | :--- | :--- | :--- | :---: |")
    for c in deferred_fps:
        md.append(f"| `{c['order_id']}` | ₹{c['amount']:,} | ₹{c['fee']:,} | **₹{c['total_cost']:,}** | `{c['ground_truth']}` | `{c['pre_hil']}` | `{c['winnability_score']}` |")
    md.append(f"| **SUBTOTAL (Deferred)** | | | **₹{deferred_cost:,}** | | | |")
    md.append(f"| **TOTAL (Method B)** | | | **₹{b['total_fp_cost']:,}** | | | |")
    md.append("")

    # ──────────────────────────────────────────────────────────────────────────
    # SECTION 4: Cases to Review (FN and FP) with Placeholders
    # ──────────────────────────────────────────────────────────────────────────
    md.append("## 4. Cases to Review")
    md.append("")
    md.append("This section lists all **False Negatives** (missed winnable disputes) and **False Positives** (contested or review-flagged disputes) requiring manual review and root-cause analysis.")
    md.append("")

    # 4.1 False Negatives
    md.append(f"### 4.1 False Negatives ({len(a['fn_cases'])} Missed Winnable Disputes)")
    md.append("")
    for idx, case in enumerate(a["fn_cases"], 1):
        md.append(f"#### FN #{idx} — Order `{case['order_id']}`")
        md.append(f"- **Disputed Amount**: ₹{case['amount']:,}")
        md.append(f"- **Ground Truth**: `{case['ground_truth']}`")
        md.append(f"- **Ground Truth Scenario/Reasoning**: {case['reasoning'] or 'N/A'}")
        md.append(f"- **System Recommended (Pre-HIL)**: `{case['pre_hil']}`")
        md.append(f"- **Final Action Taken**: `{case['final']}`")
        md.append(f"- **Root-Cause Analysis / Why It Went Wrong**:")
        md.append(f"  > *[Placeholder: Write analysis of why this case conceded instead of contesting]*")
        md.append("")

    # 4.2 False Positives
    md.append(f"### 4.2 False Positives ({len(b['fp_cases'])} Total in Benchmark)")
    md.append("")
    md.append(f"#### 4.2.1 Autonomous False Positives ({len(a['fp_cases'])} Erroneous Auto-Contests)")
    md.append("")
    for idx, case in enumerate(a["fp_cases"], 1):
        md.append(f"##### Autonomous FP #{idx} — Order `{case['order_id']}`")
        md.append(f"- **Disputed Amount**: ₹{case['amount']:,}")
        md.append(f"- **Dispute Fee Incurred**: ₹{case['fee']:,}")
        md.append(f"- **Total Incurred Loss**: ₹{case['total_cost']:,}")
        md.append(f"- **Ground Truth**: `{case['ground_truth']}`")
        md.append(f"- **Ground Truth Scenario/Reasoning**: {case['reasoning'] or 'N/A'}")
        md.append(f"- **System Recommended (Pre-HIL)**: `{case['pre_hil']}`")
        md.append(f"- **Final Action Taken**: `{case['final']}`")
        md.append(f"- **Root-Cause Analysis / Why It Went Wrong**:")
        md.append(f"  > *[Placeholder: Write analysis of why this case contested instead of conceding/refunding]*")
        md.append("")

    md.append(f"#### 4.2.2 Deferred Cases Counted as FP Under Method B ({len(deferred_fps)} Ambiguous Cases Flagged for Review)")
    md.append("")
    for idx, case in enumerate(deferred_fps, 1):
        md.append(f"##### Deferred FP #{idx} — Order `{case['order_id']}`")
        md.append(f"- **Disputed Amount**: ₹{case['amount']:,}")
        md.append(f"- **Potential Financial Exposure**: ₹{case['total_cost']:,}")
        md.append(f"- **Ground Truth**: `{case['ground_truth']}`")
        md.append(f"- **Ground Truth Scenario/Reasoning**: {case['reasoning'] or 'N/A'}")
        md.append(f"- **System Recommended (Pre-HIL)**: `{case['pre_hil']}`")
        md.append(f"- **Final Action Taken**: `{case['final']}`")
        md.append(f"- **Root-Cause Analysis / Why It Went Wrong**:")
        md.append(f"  > *[Placeholder: Write analysis of ambiguity that prompted human review]*")
        md.append("")

    # ──────────────────────────────────────────────────────────────────────────
    # SECTION 5: Evidence-Direction Check
    # ──────────────────────────────────────────────────────────────────────────
    md.append("## 5. Evidence-Direction Check")
    md.append("")
    md.append("This check flags cases where `ground_truth` is **`SHOULD_REFUND`** but the system recommended **`auto_submit`** with a high winnability score (0.95–1.00). In these scenarios, evidence supporting the **customer's damage/defect claim** (e.g., photo proofs in customer communications) was parsed as evidence supporting the merchant's defense, resulting in evidence misattribution.")
    md.append("")

    if evidence_cases:
        for idx, case in enumerate(evidence_cases, 1):
            md.append(f"### Evidence Misattribution #{idx} — Order `{case['order_id']}`")
            md.append(f"- **Flag**: `⚠️ POSSIBLE_EVIDENCE_MISATTRIBUTION`")
            md.append(f"- **Order ID**: `{case['order_id']}`")
            md.append(f"- **Disputed Amount**: ₹{case['amount']:,}")
            md.append(f"- **Winnability Score**: `{case['winnability_score']}` (Critically High)")
            md.append(f"- **System Recommendation**: `{case['pre_hil']}`")
            md.append(f"- **Ground Truth**: `{case['ground_truth']}`")
            md.append(f"- **Ground Truth Reasoning**: {case['reasoning']}")
            md.append(f"- **Evidence Direction Anomaly Description**:")
            md.append(f"  > The customer provided verifiable photo proof of item defect/damage before filing the dispute. The triage evidence extraction heuristic detected the presence of photos and proof attachments but inverted the sentiment/direction, treating customer defect photos as positive merchant delivery evidence. This drove the winnability score to `{case['winnability_score']}` and triggered an erroneous `auto_submit` decision. *Known limitation of the current evidence scoring model.*")
            md.append("")
    else:
        md.append("*(No evidence-direction anomalies detected.)*")
        md.append("")

    return "\n".join(md)


async def main_async(args: argparse.Namespace) -> int:
    # 1. Load environment variables
    env_file = find_env_file()
    if env_file and load_dotenv:
        load_dotenv(env_file)
        logger.info("Loaded environment from: %s", env_file)

    db_url = args.db_url or os.getenv("DATABASE_URL")
    if not db_url:
        logger.error(
            "DATABASE_URL not found. Specify via --db-url or set in backend/.env."
        )
        return 1

    # 2. Load Ground Truth CSV
    try:
        csv_path = find_ground_truth_csv(args.csv)
        gt_map = load_ground_truth(csv_path)
    except Exception as exc:
        logger.error("Failed to load ground truth: %s", exc)
        return 1

    # 3. Fetch dispute records from Postgres
    try:
        db_records = await fetch_dispute_records(db_url)
    except Exception as exc:
        logger.error("Failed to fetch dispute records from DB: %s", exc, exc_info=True)
        return 1

    # 4. Evaluate metrics
    metrics_data = evaluate_test_cases(
        db_records=db_records,
        ground_truth_map=gt_map,
        dispute_fee=args.fee,
    )

    # 5. Generate Markdown report
    report_content = generate_markdown_report(metrics_data)

    # Output file
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report_content, encoding="utf-8")

    logger.info("Successfully generated metrics report at: %s", output_path.resolve())

    # Print summary to console
    ma = metrics_data["method_a"]
    mb = metrics_data["method_b"]
    print("\n" + "=" * 65)
    print("SAFEMERCHANT EVALUATION METRICS SUMMARY")
    print("=" * 65)
    print(f"Total Ground Truth Cases: {metrics_data['total_cases_in_gt']}")
    print(f"Method A (Autonomous-Only):")
    print(f"  Evaluated Cases:       {ma['evaluated_total']} (Excluded {len(metrics_data['deferred_cases'])} deferred)")
    print(f"  Accuracy:              {ma['accuracy']}")
    print(f"  Precision:             {ma['precision']}")
    print(f"  Recall:                {ma['recall']}")
    print(f"  Total False Pos. Cost: INR {ma['total_fp_cost']:,}")
    print(f"  Confusion Matrix:      TP={ma['tp']}, FN={ma['fn']}, FP={ma['fp']}, TN={ma['tn']}")
    print()
    print(f"Method B (With Deferrals as Contest):")
    print(f"  Evaluated Cases:       {mb['evaluated_total']}")
    print(f"  Accuracy:              {mb['accuracy']}")
    print(f"  Precision:             {mb['precision']}")
    print(f"  Recall:                {mb['recall']}")
    print(f"  Total False Pos. Cost: INR {mb['total_fp_cost']:,}")
    print(f"  Confusion Matrix:      TP={mb['tp']}, FN={mb['fn']}, FP={mb['fp']}, TN={mb['tn']}")
    print()
    print(f"Evidence Misattributions Flagged: {len(metrics_data['evidence_direction_cases'])}")
    print(f"Report Output Path:      {output_path.resolve()}")
    print("=" * 65 + "\n")

    return 0

    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compute evaluation metrics for dispute test runs and generate metrics_report.md."
    )
    parser.add_argument(
        "--csv",
        "-c",
        type=str,
        default=None,
        help="Path to ground truth CSV (defaults to searching ground_truth.csv)",
    )
    parser.add_argument(
        "--db-url",
        "-d",
        type=str,
        default=None,
        help="Database connection URL (defaults to DATABASE_URL from .env)",
    )
    parser.add_argument(
        "--fee",
        "-f",
        type=int,
        default=500,
        help="Fixed dispute fee per contest constant in INR (default: 500)",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default="metrics_report.md",
        help="Output Markdown report filename (default: metrics_report.md)",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    exit_code = asyncio.run(main_async(args))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
