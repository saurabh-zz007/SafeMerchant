# Dispute Pipeline — Evaluation Report

## Summary
- **Total disputes**: 50
- **Correct predictions**: 50
- **Accuracy**: 100.0%

## Confusion Matrix

| Actual \ Predicted | accept_loss | auto_refund | auto_submit | human_review |
|---|---|---|---|---|
| accept_loss | 10 | 0 | 0 | 0 |
| auto_refund | 0 | 10 | 0 | 0 |
| auto_submit | 0 | 0 | 20 | 0 |
| human_review | 0 | 0 | 0 | 10 |

## Per-Class Metrics

| Class | Precision | Recall | F1 |
|---|---|---|---|
| accept_loss | 1.00 | 1.00 | 1.00 |
| auto_refund | 1.00 | 1.00 | 1.00 |
| auto_submit | 1.00 | 1.00 | 1.00 |
| human_review | 1.00 | 1.00 | 1.00 |

## False-Positive Cost Analysis

- **Contested incorrectly**: 0 cases, ₹0 total
- **Refunded incorrectly**: 0 cases, ₹0 total

## Human Review Queue

| Dispute | Predicted | Ground Truth | Score | Amount | Correct |
|---|---|---|---|---|---|
| disp_AM_007 | human_review | human_review | 75% | ₹25,659 | ✅ |
| disp_AM_001 | human_review | human_review | 75% | ₹27,601 | ✅ |
| disp_AM_004 | human_review | human_review | 75% | ₹30,256 | ✅ |
| disp_AM_009 | human_review | human_review | 75% | ₹32,496 | ✅ |
| disp_AM_010 | human_review | human_review | 75% | ₹26,215 | ✅ |
| disp_AM_002 | human_review | human_review | 75% | ₹18,003 | ✅ |
| disp_AM_003 | human_review | human_review | 75% | ₹33,965 | ✅ |
| disp_AM_008 | human_review | human_review | 75% | ₹38,283 | ✅ |
| disp_AM_005 | human_review | human_review | 75% | ₹39,911 | ✅ |
| disp_AM_006 | human_review | human_review | 75% | ₹44,714 | ✅ |
