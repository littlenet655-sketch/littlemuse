# Moderation benchmark evidence record

Copy this template for each frozen run. Replace every bracketed value; use
`NOT RUN`, `NOT AVAILABLE`, or `NOT APPLICABLE` with an explanation instead of
guessing. This record is evidence of a declared offline run, not a claim of
production effectiveness or an 18+ accuracy result.

## 1. Run identity

| Field | Value |
| --- | --- |
| Run ID | `[unique run identifier]` |
| Date/time (UTC) | `[value]` |
| Repository commit | `[full commit]` |
| Command | `python evaluate_toxicity.py --predictions [file] --output [file]` |
| Runtime / dependency lock | `[value or NOT AVAILABLE]` |
| Operator / reviewer | `[value]` |
| Result artifact SHA-256 | `[value]` |

## 2. Scope and frozen configuration

| Field | Value |
| --- | --- |
| Modality | `[TEXT / IMAGE / VIDEO / mixed]` |
| Policy version | `[config/safety_policy.yaml version]` |
| Policy SHA-256 | `[digest]` |
| Safety level | `[STANDARD / STRICT / VERY_STRICT]` |
| Detector/model versions | `[names, versions, or NOT APPLICABLE]` |
| Thresholds | `[all thresholds used]` |
| Random seed / deterministic settings | `[value or NOT APPLICABLE]` |
| Remote services | `[none or declared endpoint/version]` |

**Scope statement:** `[what this run can and cannot support]`

## 3. Dataset manifest

| Field | Value |
| --- | --- |
| Dataset name and source | `[value]` |
| License/permission | `[value]` |
| Dataset SHA-256 | `[digest]` |
| Items / modalities | `[counts]` |
| Label definitions | `[ALLOW/REVIEW/BLOCK definitions]` |
| Label provenance | `[annotators/instructions/source]` |
| Annotator agreement | `[metric or NOT AVAILABLE]` |
| Duplicate/leakage check | `[method and result]` |
| Calibration/development split | `[IDs/count/digest]` |
| Held-out evaluation split | `[IDs/count/digest]` |

**Known limitations or sampling bias:** `[value]`

## 4. Prediction and metric evidence

| Metric/artifact | Value |
| --- | --- |
| Prediction CSV path and SHA-256 | `[value]` |
| Offline item count | `[value or NOT RUN]` |
| Exact-action agreement | `[value or NOT RUN]` |
| Macro-F1 | `[value or NOT RUN]` |
| ALLOW precision / recall / F1 | `[values or NOT RUN]` |
| REVIEW precision / recall / F1 | `[values or NOT RUN]` |
| BLOCK precision / recall / F1 | `[values or NOT RUN]` |
| Confusion matrix (ALLOW, REVIEW, BLOCK order) | `[attach JSON/table]` |
| Unavailable/abstained decisions | `[count, rate, IDs, reasons]` |
| Modality/label strata | `[attach table or NOT RUN]` |
| Calibration bins/metric | `[values or NOT APPLICABLE]` |

**Dropped, unreadable, timed-out, or manually overridden items:**  
`[IDs, reasons, and resulting treatment]`

## 5. Deterministic policy checks

| Check | Result and test reference |
| --- | --- |
| Adult hard-block boundary | `[PASS/FAIL/NOT RUN + test]` |
| Dangerous-object block/review boundaries | `[PASS/FAIL/NOT RUN + test]` |
| Strictness-level routing | `[PASS/FAIL/NOT RUN + test]` |
| Total/partial failure handling | `[PASS/FAIL/NOT RUN + test]` |
| Invalid/missing evidence handling | `[PASS/FAIL/NOT RUN + test]` |

These checks validate policy routing only. They are not model-performance
items and must not be added to the offline dataset denominator.

## 6. Interpretation and outstanding validation

**What the offline result supports:**  
`[dataset- and run-specific statement]`

**What it does not support:**  
`[real-world effectiveness, generalisation, or age/adult-content performance
claim]`

**External validation still required:**  
`[independent held-out labels, subgroup/locale analysis, adversarial and
distribution-shift testing, human-review audit, privacy/safety review, and
live monitoring plan]`

**18+ accuracy claim:** `NONE — not measured or claimed by this record.`

## 7. Reviewer sign-off

| Role | Name | Date | Decision / notes |
| --- | --- | --- | --- |
| Benchmark operator | `[value]` | `[UTC]` | `[value]` |
| Independent reviewer | `[value]` | `[UTC]` | `[value]` |