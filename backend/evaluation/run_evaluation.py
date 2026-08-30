"""
Evaluation entry point.

Generates synthetic disputes → runs the full pipeline → computes metrics
→ outputs a markdown report.

Usage:
    python -m evaluation.run_evaluation
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

# Ensure the backend directory is on the path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from evaluation.metrics import compute_metrics, format_report
from evaluation.runner import run_evaluation_batch
from evaluation.synthetic_disputes import generate_synthetic_disputes

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


async def main():
    """Run the full evaluation pipeline."""
    logger.info("=" * 60)
    logger.info("SafeMerchant Dispute Pipeline — Batch Evaluation")
    logger.info("=" * 60)

    # Step 1: Generate synthetic disputes
    logger.info("Generating synthetic disputes...")
    disputes = generate_synthetic_disputes()
    logger.info("Generated %d synthetic disputes", len(disputes))

    # Print distribution
    from collections import Counter
    categories = Counter(d["ground_truth_category"] for d in disputes)
    for cat, count in sorted(categories.items()):
        logger.info("  %s: %d", cat, count)

    # Step 2: Run the pipeline
    logger.info("\nRunning pipeline over %d disputes...", len(disputes))
    results = await run_evaluation_batch(disputes, concurrency=3)
    logger.info("Pipeline complete — %d results collected", len(results))

    # Step 3: Compute metrics
    logger.info("\nComputing metrics...")
    report = compute_metrics(results)

    # Step 4: Format and output report
    report_text = format_report(report)

    # Print to stdout (handle Windows encoding)
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    print("\n")
    print(report_text)

    # Save to file
    results_dir = Path(__file__).resolve().parent / "results"
    results_dir.mkdir(exist_ok=True)
    report_path = results_dir / "report.md"
    report_path.write_text(report_text, encoding="utf-8")
    logger.info("\nReport saved to %s", report_path)

    # Return exit code based on accuracy
    if report.accuracy >= 0.7:
        logger.info("✅ Evaluation PASSED (accuracy %.1f%%)", report.accuracy * 100)
        return 0
    else:
        logger.warning("⚠️ Evaluation accuracy below 70%%: %.1f%%", report.accuracy * 100)
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
