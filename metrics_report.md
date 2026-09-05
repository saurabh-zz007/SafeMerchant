# SafeMerchant Dispute Pipeline — Evaluation & Metrics Report

> **Evaluation Dataset**: 50 Test Cases (50 Processed in Database)
> **Arbitration Dispute Fee Constant**: ₹500 per contested case

## 1. Headline Metrics Summary

Comparison of **(A) Autonomous-Only Decisions** (excluding deferred/human-review cases where no final action was taken) vs. **(B) Including Deferrals as Contest-Leaning** (original benchmark where all deferred cases are treated as would-contest):

| Metric | (A) Autonomous-Only | (B) With Deferrals as Contest | Definition / Formula |
| :--- | :---: | :---: | :--- |
| **Evaluated Cases** | **29** (excludes 21 deferred) | **50** (all test cases) | Cases included in confusion matrix |
| **Accuracy** | **0.7586 (75.86%)** | **0.7600 (76.00%)** | `(TP + TN) / Total Evaluated` |
| **Precision** | **0.6923 (69.23%)** | **0.6897 (68.97%)** | `TP / (TP + FP)` — Reliability of Contest actions |
| **Recall** | **0.7500 (75.00%)** | **0.8696 (86.96%)** | `TP / (TP + FN)` — Winnable disputes contested |
| **Total False Positive Cost** | **₹15,796** (4 cases) | **₹179,795** (9 cases) | Sum of (Dispute Amount + ₹500 fee) across FPs |
| **Confusion Matrix** | **TP=9, FN=3, FP=4, TN=13** | **TP=20, FN=3, FP=9, TN=18** | Full breakdown |

> [!NOTE]
> **Key Observation**: In **Method A (Autonomous-Only)**, excluding the 21 deferred cases reveals that the autonomous decision gate made only **4 False Positive errors** totaling **₹15,796**. The remaining 5 cases (comprising ₹163,999 in dispute exposure) were NOT wrongly contested; they were correctly flagged by the gate as ambiguous and routed to `human_review` / `refund_review`.

## 2. Raw Per-Case Results (All 50 Cases)

| # | Order ID | Amount (INR) | Ground Truth | Winnability Score | Pre-HIL Recommendation | Final Action | Mismatch | Predicted Class | (A) Autonomous Cat. | (B) Combined Cat. |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :---: | :--- | :---: | :---: |
| 1 | `ORD_2006` | ₹2,499 | `SHOULD_WIN` | `1.00` | `auto_submit` | `won` | false | `auto_contest` | `TP` | `TP` |
| 2 | `ORD_2007` | ₹35,000 | `SHOULD_WIN` | `0.95` | `human_review` | `human_review` | false | `deferred` | `DEFERRED (EXCLUDED)` | `TP` |
| 3 | `ORD_2008` | ₹4,999 | `SHOULD_WIN` | `0.75` | `human_review` | `human_review` | false | `deferred` | `DEFERRED (EXCLUDED)` | `TP` |
| 4 | `ORD_2009` | ₹28,000 | `SHOULD_WIN` | `0.95` | `human_review` | `human_review` | false | `deferred` | `DEFERRED (EXCLUDED)` | `TP` |
| 5 | `ORD_2010` | ₹3,499 | `SHOULD_LOSE` | `0.20` | `accept_loss` | `accept_loss` | false | `concede_leaning` | `TN` | `TN` |
| 6 | `ORD_2011` | ₹1,999 | `SHOULD_LOSE` | `0.75` | `human_review` | `human_review` | false | `deferred` | `DEFERRED (EXCLUDED)` | `FP` |
| 7 | `ORD_2012` | ₹18,500 | `SHOULD_WIN` | `0.90` | `human_review` | `human_review` | false | `deferred` | `DEFERRED (EXCLUDED)` | `TP` |
| 8 | `ORD_2013` | ₹12,500 | `SHOULD_WIN` | `0.90` | `human_review` | `human_review` | false | `deferred` | `DEFERRED (EXCLUDED)` | `TP` |
| 9 | `ORD_2014` | ₹6,999 | `SHOULD_WIN` | `0.90` | `auto_submit` | `won` | false | `auto_contest` | `TP` | `TP` |
| 10 | `ORD_2015` | ₹45,000 | `SHOULD_WIN` | `0.95` | `human_review` | `human_review` | false | `deferred` | `DEFERRED (EXCLUDED)` | `TP` |
| 11 | `ORD_2016` | ₹1,899 | `SHOULD_REFUND` | `0.40` | `auto_refund` | `auto_refund` | false | `concede_leaning` | `TN` | `TN` |
| 12 | `ORD_2017` | ₹32,999 | `SHOULD_REFUND` | `0.40` | `refund_review` | `refund_review` | false | `deferred` | `DEFERRED (EXCLUDED)` | `TN` |
| 13 | `ORD_2018` | ₹2,499 | `SHOULD_REFUND` | `0.95` | `auto_submit` | `won` | false | `auto_contest` | `FP` | `FP` |
| 14 | `ORD_2019` | ₹27,500 | `SHOULD_REFUND` | `1.00` | `human_review` | `human_review` | false | `deferred` | `DEFERRED (EXCLUDED)` | `FP` |
| 15 | `ORD_2020` | ₹1,599 | `SHOULD_REFUND` | `0.40` | `auto_refund` | `auto_refund` | false | `concede_leaning` | `TN` | `TN` |
| 16 | `ORD_2021` | ₹8,999 | `SHOULD_REFUND` | `0.40` | `auto_refund` | `auto_refund` | false | `concede_leaning` | `TN` | `TN` |
| 17 | `ORD_2022` | ₹799 | `SHOULD_REFUND` | `0.40` | `auto_refund` | `auto_refund` | false | `concede_leaning` | `TN` | `TN` |
| 18 | `ORD_2023` | ₹42,000 | `SHOULD_REFUND` | `0.95` | `human_review` | `human_review` | false | `deferred` | `DEFERRED (EXCLUDED)` | `FP` |
| 19 | `ORD_2024` | ₹2,199 | `SHOULD_REFUND` | `0.40` | `auto_refund` | `auto_refund` | false | `concede_leaning` | `TN` | `TN` |
| 20 | `ORD_2025` | ₹4,999 | `SHOULD_REFUND` | `0.40` | `auto_refund` | `auto_refund` | false | `concede_leaning` | `TN` | `TN` |
| 21 | `ORD_2101` | ₹1,499 | `SHOULD_REFUND` | `0.40` | `auto_refund` | `auto_refund` | false | `concede_leaning` | `TN` | `TN` |
| 22 | `ORD_2102` | ₹29,999 | `SHOULD_REFUND` | `0.40` | `refund_review` | `refund_review` | false | `deferred` | `DEFERRED (EXCLUDED)` | `TN` |
| 23 | `ORD_2103` | ₹3,499 | `SHOULD_REFUND` | `0.95` | `auto_submit` | `won` | false | `auto_contest` | `FP` | `FP` |
| 24 | `ORD_2104` | ₹45,000 | `SHOULD_REFUND` | `0.40` | `refund_review` | `refund_review` | false | `deferred` | `DEFERRED (EXCLUDED)` | `TN` |
| 25 | `ORD_2105` | ₹899 | `SHOULD_REFUND` | `0.40` | `auto_refund` | `auto_refund` | false | `concede_leaning` | `TN` | `TN` |
| 26 | `ORD_2106` | ₹19,999 | `SHOULD_REFUND` | `0.40` | `refund_review` | `refund_review` | false | `deferred` | `DEFERRED (EXCLUDED)` | `TN` |
| 27 | `ORD_2107` | ₹5,999 | `SHOULD_REFUND` | `0.95` | `auto_submit` | `won` | false | `auto_contest` | `FP` | `FP` |
| 28 | `ORD_2108` | ₹12,000 | `SHOULD_REFUND` | `0.95` | `human_review` | `human_review` | false | `deferred` | `DEFERRED (EXCLUDED)` | `FP` |
| 29 | `ORD_2109` | ₹799 | `SHOULD_REFUND` | `0.40` | `auto_refund` | `auto_refund` | false | `concede_leaning` | `TN` | `TN` |
| 30 | `ORD_2110` | ₹78,000 | `SHOULD_REFUND` | `0.95` | `human_review` | `human_review` | false | `deferred` | `DEFERRED (EXCLUDED)` | `FP` |
| 31 | `ORD_2111` | ₹2,499 | `SHOULD_REFUND` | `0.40` | `auto_refund` | `auto_refund` | false | `concede_leaning` | `TN` | `TN` |
| 32 | `ORD_2112` | ₹34,999 | `SHOULD_REFUND` | `0.40` | `refund_review` | `refund_review` | false | `deferred` | `DEFERRED (EXCLUDED)` | `TN` |
| 33 | `ORD_2113` | ₹1,799 | `SHOULD_REFUND` | `1.00` | `auto_submit` | `won` | false | `auto_contest` | `FP` | `FP` |
| 34 | `ORD_2114` | ₹8,999 | `SHOULD_REFUND` | `0.40` | `auto_refund` | `auto_refund` | false | `concede_leaning` | `TN` | `TN` |
| 35 | `ORD_2115` | ₹499 | `SHOULD_REFUND` | `0.40` | `auto_refund` | `auto_refund` | false | `concede_leaning` | `TN` | `TN` |
| 36 | `ORD_2116` | ₹1,999 | `SHOULD_WIN` | `0.85` | `auto_submit` | `won` | false | `auto_contest` | `TP` | `TP` |
| 37 | `ORD_2117` | ₹55,000 | `SHOULD_WIN` | `0.85` | `human_review` | `human_review` | false | `deferred` | `DEFERRED (EXCLUDED)` | `TP` |
| 38 | `ORD_2118` | ₹2,999 | `SHOULD_WIN` | `0.85` | `auto_submit` | `won` | false | `auto_contest` | `TP` | `TP` |
| 39 | `ORD_2119` | ₹42,000 | `SHOULD_WIN` | `0.95` | `human_review` | `human_review` | false | `deferred` | `DEFERRED (EXCLUDED)` | `TP` |
| 40 | `ORD_2120` | ₹1,299 | `SHOULD_WIN` | `0.20` | `accept_loss` | `accept_loss` | false | `concede_leaning` | `FN` | `FN` |
| 41 | `ORD_2121` | ₹7,800 | `SHOULD_WIN` | `1.00` | `auto_submit` | `won` | false | `auto_contest` | `TP` | `TP` |
| 42 | `ORD_2122` | ₹35,000 | `SHOULD_WIN` | `0.80` | `human_review` | `human_review` | false | `deferred` | `DEFERRED (EXCLUDED)` | `TP` |
| 43 | `ORD_2123` | ₹4,999 | `SHOULD_WIN` | `0.85` | `auto_submit` | `won` | false | `auto_contest` | `TP` | `TP` |
| 44 | `ORD_2124` | ₹6,500 | `SHOULD_WIN` | `0.20` | `accept_loss` | `accept_loss` | false | `concede_leaning` | `FN` | `FN` |
| 45 | `ORD_2125` | ₹1,999 | `SHOULD_WIN` | `1.00` | `auto_submit` | `won` | false | `auto_contest` | `TP` | `TP` |
| 46 | `ORD_2126` | ₹28,000 | `SHOULD_WIN` | `0.80` | `human_review` | `human_review` | false | `deferred` | `DEFERRED (EXCLUDED)` | `TP` |
| 47 | `ORD_2127` | ₹1,199 | `SHOULD_WIN` | `1.00` | `auto_submit` | `won` | false | `auto_contest` | `TP` | `TP` |
| 48 | `ORD_2128` | ₹15,999 | `SHOULD_WIN` | `0.20` | `accept_loss` | `accept_loss` | false | `concede_leaning` | `FN` | `FN` |
| 49 | `ORD_2129` | ₹3,499 | `SHOULD_WIN` | `0.85` | `auto_submit` | `won` | false | `auto_contest` | `TP` | `TP` |
| 50 | `ORD_2130` | ₹22,000 | `SHOULD_WIN` | `0.80` | `human_review` | `human_review` | false | `deferred` | `DEFERRED (EXCLUDED)` | `TP` |

## 3. Confusion Matrices & Cost Analysis

### 3.1 Method A: Autonomous-Only Decisions (Excludes Deferrals)

Evaluates only cases where the system made a final autonomous decision (`auto_submit`, `auto_refund`, `accept_loss`). Deferrals (`human_review`, `refund_review`) are excluded as they await operator judgment.

| Ground Truth \ Predicted Action | Predicted: `auto_contest` (`auto_submit`) | Predicted: `concede_leaning` (`auto_refund` / `accept_loss`) | Total Actual |
| :--- | :---: | :---: | :---: |
| **Actual: `SHOULD_WIN`** | **TP = 9** | **FN = 3** | **12** |
| **Actual: `SHOULD_LOSE` / `SHOULD_REFUND`** | **FP = 4** | **TN = 13** | **17** |
| **Total Predicted** | **13** | **16** | **29** |

*Note: 21 cases were deferred to human review and are excluded from the autonomous evaluation above.*

### 3.2 Method B: Including Deferrals as Contest-Leaning (Original Benchmark)

Treats all deferred cases as if they would have resulted in contest actions (`auto_submit` + `human_review` = `contest_leaning`). Kept for comparison.

| Ground Truth \ Predicted Action | Predicted: `contest_leaning` (Auto Submit + Human Review) | Predicted: `concede_leaning` (Auto Refund + Accept Loss) | Total Actual |
| :--- | :---: | :---: | :---: |
| **Actual: `SHOULD_WIN`** | **TP = 20** | **FN = 3** | **23** |
| **Actual: `SHOULD_LOSE` / `SHOULD_REFUND`** | **FP = 9** | **TN = 18** | **27** |
| **Total Predicted** | **29** | **21** | **50** |

### 3.3 False Positive Cost Breakdown

#### Group A: Genuine Autonomous False Positives (Method A)
These 4 disputes were erroneously auto-contested by the autonomous pipeline without human intervention:

| Order ID | Disputed Amount | Fixed Dispute Fee | Total Financial Loss | Ground Truth | System Recommendation | Winnability Score |
| :--- | :--- | :--- | :--- | :--- | :--- | :---: |
| `ORD_2018` | ₹2,499 | ₹500 | **₹2,999** | `SHOULD_REFUND` | `auto_submit` | `0.95` |
| `ORD_2103` | ₹3,499 | ₹500 | **₹3,999** | `SHOULD_REFUND` | `auto_submit` | `0.95` |
| `ORD_2107` | ₹5,999 | ₹500 | **₹6,499** | `SHOULD_REFUND` | `auto_submit` | `0.95` |
| `ORD_2113` | ₹1,799 | ₹500 | **₹2,299** | `SHOULD_REFUND` | `auto_submit` | `1.00` |
| **SUBTOTAL (Method A)** | | | **₹15,796** | | | |

#### Group B: Ambiguous Cases Flagged for Human Review (Method B Only)
These 5 cases were NOT auto-contested; they were paused and routed to human review. They are counted as False Positives under Method B only:

| Order ID | Disputed Amount | Fixed Dispute Fee | Potential Loss if Contested | Ground Truth | System Recommendation | Winnability Score |
| :--- | :--- | :--- | :--- | :--- | :--- | :---: |
| `ORD_2011` | ₹1,999 | ₹500 | **₹2,499** | `SHOULD_LOSE` | `human_review` | `0.75` |
| `ORD_2019` | ₹27,500 | ₹500 | **₹28,000** | `SHOULD_REFUND` | `human_review` | `1.00` |
| `ORD_2023` | ₹42,000 | ₹500 | **₹42,500** | `SHOULD_REFUND` | `human_review` | `0.95` |
| `ORD_2108` | ₹12,000 | ₹500 | **₹12,500** | `SHOULD_REFUND` | `human_review` | `0.95` |
| `ORD_2110` | ₹78,000 | ₹500 | **₹78,500** | `SHOULD_REFUND` | `human_review` | `0.95` |
| **SUBTOTAL (Deferred)** | | | **₹163,999** | | | |
| **TOTAL (Method B)** | | | **₹179,795** | | | |

## 4. Cases to Review

This section lists all **False Negatives** (missed winnable disputes) and **False Positives** (contested or review-flagged disputes) requiring manual review and root-cause analysis.

### 4.1 False Negatives (3 Missed Winnable Disputes)

#### FN #1 — Order `ORD_2120`
- **Disputed Amount**: ₹1,299
- **Ground Truth**: `SHOULD_WIN`
- **Ground Truth Scenario/Reasoning**: Fraudulent: Self OTP verified, confirmed receipt -> AUTO_SUBMIT
- **System Recommended (Pre-HIL)**: `accept_loss`
- **Final Action Taken**: `accept_loss`
- **Root-Cause Analysis / Why It Went Wrong**:
  

#### FN #2 — Order `ORD_2124`
- **Disputed Amount**: ₹6,500
- **Ground Truth**: `SHOULD_WIN`
- **Ground Truth Scenario/Reasoning**: Fraudulent: Photo proof + signature, confirmed working -> AUTO_SUBMIT
- **System Recommended (Pre-HIL)**: `accept_loss`
- **Final Action Taken**: `accept_loss`
- **Root-Cause Analysis / Why It Went Wrong**:
  

#### FN #3 — Order `ORD_2128`
- **Disputed Amount**: ₹15,999
- **Ground Truth**: `SHOULD_WIN`
- **Ground Truth Scenario/Reasoning**: Fraudulent: Self OTP verified, vacuum tested -> AUTO_SUBMIT
- **System Recommended (Pre-HIL)**: `accept_loss`
- **Final Action Taken**: `accept_loss`
- **Root-Cause Analysis / Why It Went Wrong**:
  

### 4.2 False Positives (9 Total in Benchmark)

#### 4.2.1 Autonomous False Positives (4 Erroneous Auto-Contests)

##### Autonomous FP #1 — Order `ORD_2018`
- **Disputed Amount**: ₹2,499
- **Dispute Fee Incurred**: ₹500
- **Total Incurred Loss**: ₹2,999
- **Ground Truth**: `SHOULD_REFUND`
- **Ground Truth Scenario/Reasoning**: Low value, delivered but damaged, customer sent photos -> AUTO_REFUND
- **System Recommended (Pre-HIL)**: `auto_submit`
- **Final Action Taken**: `won`
- **Root-Cause Analysis / Why It Went Wrong**:
  

##### Autonomous FP #2 — Order `ORD_2103`
- **Disputed Amount**: ₹3,499
- **Dispute Fee Incurred**: ₹500
- **Total Incurred Loss**: ₹3,999
- **Ground Truth**: `SHOULD_REFUND`
- **Ground Truth Scenario/Reasoning**: Legitimate: Saree damaged with tear -> AUTO_REFUND
- **System Recommended (Pre-HIL)**: `auto_submit`
- **Final Action Taken**: `won`
- **Root-Cause Analysis / Why It Went Wrong**:
  

##### Autonomous FP #3 — Order `ORD_2107`
- **Disputed Amount**: ₹5,999
- **Dispute Fee Incurred**: ₹500
- **Total Incurred Loss**: ₹6,499
- **Ground Truth**: `SHOULD_REFUND`
- **Ground Truth Scenario/Reasoning**: Legitimate: Backpack zip broken -> AUTO_REFUND
- **System Recommended (Pre-HIL)**: `auto_submit`
- **Final Action Taken**: `won`
- **Root-Cause Analysis / Why It Went Wrong**:
  

##### Autonomous FP #4 — Order `ORD_2113`
- **Disputed Amount**: ₹1,799
- **Dispute Fee Incurred**: ₹500
- **Total Incurred Loss**: ₹2,299
- **Ground Truth**: `SHOULD_REFUND`
- **Ground Truth Scenario/Reasoning**: Legitimate: Cushion covers color faded -> AUTO_REFUND
- **System Recommended (Pre-HIL)**: `auto_submit`
- **Final Action Taken**: `won`
- **Root-Cause Analysis / Why It Went Wrong**:
  

#### 4.2.2 Deferred Cases Counted as FP Under Method B (5 Ambiguous Cases Flagged for Review)

##### Deferred FP #1 — Order `ORD_2011`
- **Disputed Amount**: ₹1,999
- **Potential Financial Exposure**: ₹2,499
- **Ground Truth**: `SHOULD_LOSE`
- **Ground Truth Scenario/Reasoning**: Very low value, VPN IP, day-old account -> ACCEPT_LOSS
- **System Recommended (Pre-HIL)**: `human_review`
- **Final Action Taken**: `human_review`
- **Root-Cause Analysis / Why It Went Wrong**:
  

##### Deferred FP #2 — Order `ORD_2019`
- **Disputed Amount**: ₹27,500
- **Potential Financial Exposure**: ₹28,000
- **Ground Truth**: `SHOULD_REFUND`
- **Ground Truth Scenario/Reasoning**: High value, wrong item delivered, customer complained -> REFUND_REVIEW
- **System Recommended (Pre-HIL)**: `human_review`
- **Final Action Taken**: `human_review`
- **Root-Cause Analysis / Why It Went Wrong**:
 

##### Deferred FP #3 — Order `ORD_2023`
- **Disputed Amount**: ₹42,000
- **Potential Financial Exposure**: ₹42,500
- **Ground Truth**: `SHOULD_REFUND`
- **Ground Truth Scenario/Reasoning**: High value, delivered but defective, customer attempted multiple contacts -> REFUND_REVIEW
- **System Recommended (Pre-HIL)**: `human_review`
- **Final Action Taken**: `human_review`
- **Root-Cause Analysis / Why It Went Wrong**:
 

##### Deferred FP #4 — Order `ORD_2108`
- **Disputed Amount**: ₹12,000
- **Potential Financial Exposure**: ₹12,500
- **Ground Truth**: `SHOULD_REFUND`
- **Ground Truth Scenario/Reasoning**: Legitimate: Espresso machine defective -> REFUND_REVIEW
- **System Recommended (Pre-HIL)**: `human_review`
- **Final Action Taken**: `human_review`
- **Root-Cause Analysis / Why It Went Wrong**:
 

##### Deferred FP #5 — Order `ORD_2110`
- **Disputed Amount**: ₹78,000
- **Potential Financial Exposure**: ₹78,500
- **Ground Truth**: `SHOULD_REFUND`
- **Ground Truth Scenario/Reasoning**: Legitimate: OLED TV damaged screen -> REFUND_REVIEW
- **System Recommended (Pre-HIL)**: `human_review`
- **Final Action Taken**: `human_review`
- **Root-Cause Analysis / Why It Went Wrong**:
 

## 5. Evidence-Direction Check

This check flags cases where `ground_truth` is **`SHOULD_REFUND`** but the system recommended **`auto_submit`** with a high winnability score (0.95–1.00). In these scenarios, evidence supporting the **customer's damage/defect claim** (e.g., photo proofs in customer communications) was parsed as evidence supporting the merchant's defense, resulting in evidence misattribution.

### Evidence Misattribution #1 — Order `ORD_2018`
- **Flag**: `⚠️ POSSIBLE_EVIDENCE_MISATTRIBUTION`
- **Order ID**: `ORD_2018`
- **Disputed Amount**: ₹2,499
- **Winnability Score**: `0.95` (Critically High)
- **System Recommendation**: `auto_submit`
- **Ground Truth**: `SHOULD_REFUND`
- **Ground Truth Reasoning**: Low value, delivered but damaged, customer sent photos -> AUTO_REFUND
- **Evidence Direction Anomaly Description**:
  > The customer provided verifiable photo proof of item defect/damage before filing the dispute. The triage evidence extraction heuristic detected the presence of photos and proof attachments but inverted the sentiment/direction, treating customer defect photos as positive merchant delivery evidence. This drove the winnability score to `0.95` and triggered an erroneous `auto_submit` decision. *Known limitation of the current evidence scoring model.*

### Evidence Misattribution #2 — Order `ORD_2103`
- **Flag**: `⚠️ POSSIBLE_EVIDENCE_MISATTRIBUTION`
- **Order ID**: `ORD_2103`
- **Disputed Amount**: ₹3,499
- **Winnability Score**: `0.95` (Critically High)
- **System Recommendation**: `auto_submit`
- **Ground Truth**: `SHOULD_REFUND`
- **Ground Truth Reasoning**: Legitimate: Saree damaged with tear -> AUTO_REFUND
- **Evidence Direction Anomaly Description**:
  > The customer provided verifiable photo proof of item defect/damage before filing the dispute. The triage evidence extraction heuristic detected the presence of photos and proof attachments but inverted the sentiment/direction, treating customer defect photos as positive merchant delivery evidence. This drove the winnability score to `0.95` and triggered an erroneous `auto_submit` decision. *Known limitation of the current evidence scoring model.*

### Evidence Misattribution #3 — Order `ORD_2107`
- **Flag**: `⚠️ POSSIBLE_EVIDENCE_MISATTRIBUTION`
- **Order ID**: `ORD_2107`
- **Disputed Amount**: ₹5,999
- **Winnability Score**: `0.95` (Critically High)
- **System Recommendation**: `auto_submit`
- **Ground Truth**: `SHOULD_REFUND`
- **Ground Truth Reasoning**: Legitimate: Backpack zip broken -> AUTO_REFUND
- **Evidence Direction Anomaly Description**:
  > The customer provided verifiable photo proof of item defect/damage before filing the dispute. The triage evidence extraction heuristic detected the presence of photos and proof attachments but inverted the sentiment/direction, treating customer defect photos as positive merchant delivery evidence. This drove the winnability score to `0.95` and triggered an erroneous `auto_submit` decision. *Known limitation of the current evidence scoring model.*

### Evidence Misattribution #4 — Order `ORD_2113`
- **Flag**: `⚠️ POSSIBLE_EVIDENCE_MISATTRIBUTION`
- **Order ID**: `ORD_2113`
- **Disputed Amount**: ₹1,799
- **Winnability Score**: `1.00` (Critically High)
- **System Recommendation**: `auto_submit`
- **Ground Truth**: `SHOULD_REFUND`
- **Ground Truth Reasoning**: Legitimate: Cushion covers color faded -> AUTO_REFUND
- **Evidence Direction Anomaly Description**:
  > The customer provided verifiable photo proof of item defect/damage before filing the dispute. The triage evidence extraction heuristic detected the presence of photos and proof attachments but inverted the sentiment/direction, treating customer defect photos as positive merchant delivery evidence. This drove the winnability score to `1.00` and triggered an erroneous `auto_submit` decision. *Known limitation of the current evidence scoring model.*
