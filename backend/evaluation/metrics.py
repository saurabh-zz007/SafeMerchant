"""
Evaluation metrics — precision, recall, F1, confusion matrix, false-positive cost.

Computes classification metrics across the dispute pipeline's gate actions.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ClassMetrics:
    """Per-class precision, recall, F1."""

    label: str
    true_positives: int = 0
    false_positives: int = 0
    false_negatives: int = 0

    @property
    def precision(self) -> float:
        denom = self.true_positives + self.false_positives
        return self.true_positives / denom if denom > 0 else 0.0

    @property
    def recall(self) -> float:
        denom = self.true_positives + self.false_negatives
        return self.true_positives / denom if denom > 0 else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return (2 * p * r) / (p + r) if (p + r) > 0 else 0.0


@dataclass
class FalsePositiveCost:
    """Cost of false positives (contesting or refunding incorrectly)."""

    contested_incorrectly_count: int = 0
    contested_incorrectly_amount: int = 0
    refunded_incorrectly_count: int = 0
    refunded_incorrectly_amount: int = 0


@dataclass
class EvaluationReport:
    """Complete evaluation report."""

    total_disputes: int = 0
    correct_predictions: int = 0
    accuracy: float = 0.0
    confusion_matrix: dict[str, dict[str, int]] = field(default_factory=dict)
    class_metrics: list[ClassMetrics] = field(default_factory=list)
    false_positive_cost: FalsePositiveCost = field(default_factory=FalsePositiveCost)
    exception_list: list[dict[str, Any]] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)


def compute_metrics(results: list[dict[str, Any]]) -> EvaluationReport:
    """
    Compute evaluation metrics from pipeline results.

    Args:
        results: List of dicts from run_evaluation_batch, each with:
            - ground_truth: expected gate_action
            - predicted_action: actual gate_action from pipeline
            - amount: dispute amount
            - dispute_id, error, etc.

    Returns:
        EvaluationReport with confusion matrix, per-class metrics,
        false-positive costs, and exception list.
    """
    report = EvaluationReport()
    report.total_disputes = len(results)

    # Collect all labels
    all_labels = sorted(set(
        [r["ground_truth"] for r in results]
        + [r["predicted_action"] for r in results]
    ))

    # Build confusion matrix
    cm: dict[str, dict[str, int]] = {
        gt: {pred: 0 for pred in all_labels} for gt in all_labels
    }
    for r in results:
        gt = r["ground_truth"]
        pred = r["predicted_action"]
        if gt in cm and pred in cm[gt]:
            cm[gt][pred] += 1
    report.confusion_matrix = cm

    # Compute per-class metrics
    class_stats: dict[str, ClassMetrics] = {
        label: ClassMetrics(label=label) for label in all_labels
    }

    for r in results:
        gt = r["ground_truth"]
        pred = r["predicted_action"]
        if gt == pred:
            report.correct_predictions += 1
            class_stats[gt].true_positives += 1
        else:
            class_stats[gt].false_negatives += 1
            if pred in class_stats:
                class_stats[pred].false_positives += 1

    report.accuracy = (
        report.correct_predictions / report.total_disputes
        if report.total_disputes > 0
        else 0.0
    )
    report.class_metrics = list(class_stats.values())

    # Compute false-positive costs
    fpc = FalsePositiveCost()
    for r in results:
        gt = r["ground_truth"]
        pred = r["predicted_action"]
        amount = r.get("amount", 0)

        # Contested when should have been accept_loss or refund
        if pred in ("auto_submit",) and gt in ("accept_loss", "auto_refund", "refund_review"):
            fpc.contested_incorrectly_count += 1
            fpc.contested_incorrectly_amount += amount

        # Refunded when should have been contest or accept_loss
        if pred in ("auto_refund",) and gt in ("auto_submit", "human_review"):
            fpc.refunded_incorrectly_count += 1
            fpc.refunded_incorrectly_amount += amount

    report.false_positive_cost = fpc

    # Exception list — cases routed to human_review
    for r in results:
        if r["predicted_action"] in ("human_review", "refund_review"):
            report.exception_list.append({
                "dispute_id": r["dispute_id"],
                "predicted_action": r["predicted_action"],
                "ground_truth": r["ground_truth"],
                "winnability_score": r.get("winnability_score", 0.0),
                "amount": r.get("amount", 0),
                "correct": r["correct"],
            })

    # Collect errors
    for r in results:
        if r.get("error"):
            report.errors.append({
                "dispute_id": r["dispute_id"],
                "error": r["error"],
            })

    return report


def format_report(report: EvaluationReport) -> str:
    """Format the evaluation report as a readable markdown string."""
    lines = []
    lines.append("# Dispute Pipeline — Evaluation Report")
    lines.append("")

    # Summary
    lines.append("## Summary")
    lines.append(f"- **Total disputes**: {report.total_disputes}")
    lines.append(f"- **Correct predictions**: {report.correct_predictions}")
    lines.append(f"- **Accuracy**: {report.accuracy:.1%}")
    lines.append("")

    # Confusion Matrix
    lines.append("## Confusion Matrix")
    lines.append("")
    all_labels = sorted(report.confusion_matrix.keys())
    header = "| Actual \\ Predicted | " + " | ".join(all_labels) + " |"
    separator = "|" + "---|" * (len(all_labels) + 1)
    lines.append(header)
    lines.append(separator)
    for gt in all_labels:
        row_values = [str(report.confusion_matrix[gt].get(pred, 0)) for pred in all_labels]
        lines.append(f"| {gt} | " + " | ".join(row_values) + " |")
    lines.append("")

    # Per-class metrics
    lines.append("## Per-Class Metrics")
    lines.append("")
    lines.append("| Class | Precision | Recall | F1 |")
    lines.append("|---|---|---|---|")
    for cm in report.class_metrics:
        lines.append(
            f"| {cm.label} | {cm.precision:.2f} | {cm.recall:.2f} | {cm.f1:.2f} |"
        )
    lines.append("")

    # False-positive costs
    fpc = report.false_positive_cost
    lines.append("## False-Positive Cost Analysis")
    lines.append("")
    lines.append(f"- **Contested incorrectly**: {fpc.contested_incorrectly_count} cases, "
                 f"₹{fpc.contested_incorrectly_amount:,} total")
    lines.append(f"- **Refunded incorrectly**: {fpc.refunded_incorrectly_count} cases, "
                 f"₹{fpc.refunded_incorrectly_amount:,} total")
    lines.append("")

    # Exception list
    if report.exception_list:
        lines.append("## Human Review Queue")
        lines.append("")
        lines.append("| Dispute | Predicted | Ground Truth | Score | Amount | Correct |")
        lines.append("|---|---|---|---|---|---|")
        for exc in report.exception_list:
            lines.append(
                f"| {exc['dispute_id']} | {exc['predicted_action']} | "
                f"{exc['ground_truth']} | {exc.get('winnability_score', 0):.0%} | "
                f"₹{exc.get('amount', 0):,} | {'✅' if exc['correct'] else '❌'} |"
            )
        lines.append("")

    # Errors
    if report.errors:
        lines.append("## Pipeline Errors")
        lines.append("")
        for err in report.errors:
            lines.append(f"- **{err['dispute_id']}**: {err['error']}")
        lines.append("")

    return "\n".join(lines)
