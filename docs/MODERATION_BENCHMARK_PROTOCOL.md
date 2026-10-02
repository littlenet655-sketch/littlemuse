# LittleNet moderation benchmark and calibration protocol

**Status:** readiness protocol; no benchmark result is asserted by this document.  
**Purpose:** make a frozen, reviewable offline moderation run possible without
training or silently presenting a small fixture as production evidence.

## What this protocol measures

The unit under evaluation is the complete decision contract for a declared
modality and dataset split:

```text
frozen detector outputs/evidence → safety policy → ALLOW | REVIEW | BLOCK
```

The benchmark runner is `evaluate_toxicity.py`. Despite its historical
filename, it does not download a model, train a model, choose a dataset
subset, or invent labels. It accepts a prediction export with these required
columns:

```text
id, expected_action, predicted_action
```

Actions must be `ALLOW`, `REVIEW`, or `BLOCK`. IDs must be unique. Scores and
evidence may be kept in the source export, but they are not interpreted by the
runner unless a future protocol explicitly defines their semantics.

## Required run record

Every submitted result must include the completed
`MODERATION_BENCHMARK_EVIDENCE_TEMPLATE.md` and:

1. **Frozen code and policy:** repository commit, policy version and SHA-256
   digest of `config/safety_policy.yaml`.
2. **Frozen model/dependency state:** each model name/version or an explicit
   `not applicable` for a policy-only fixture; dependency lock/hash and
   inference settings.
3. **Dataset manifest:** source and license, dataset digest, item count,
   modalities, label definitions, class counts, annotation instructions,
   annotator agreement (if available), and duplicate/leakage checks.
4. **Split declaration:** development/calibration and held-out evaluation
   items must be disjoint. Do not tune thresholds on the held-out split.
5. **Prediction export:** the exact CSV supplied to the runner, including
   per-item evidence/score provenance where permitted.
6. **Command and environment:** command, Python/runtime version, hardware,
   random seeds, and whether remote services were used.
7. **Exceptions:** dropped, unreadable, abstained, timed-out, or manually
   overridden items, with IDs and reasons. Never silently remove failures.

## Minimum offline metrics

Report the runner's fixed action order (`ALLOW`, `REVIEW`, `BLOCK`):

- item count and offline exact-action agreement;
- confusion matrix;
- per-action support, precision, recall and F1;
- macro-F1;
- count/rate of unavailable or abstained decisions, if the system can emit
  them (these must not be converted to `ALLOW`);
- threshold values and the policy action they produce.

For a calibrated score, also report reliability bins, bin counts and a
calibration metric selected before looking at results. Only report score
calibration when the score has a documented probability interpretation.
Otherwise call it a detector score/evidence score and do not describe it as a
probability.

The benchmark must be stratified by at least modality and policy-relevant
label family when the dataset supports those labels. Report the unstratified
aggregate only alongside the strata; an aggregate can hide a failed safety
class.

## Thresholds are policy, not accuracy

`adult_block`, `weapon_review`, `weapon_block`, and the
`STANDARD`/`STRICT`/`VERY_STRICT` levels are policy thresholds. A threshold
test demonstrates deterministic routing at a boundary; it does not establish
that the underlying detector is correct. Threshold changes require a new
policy digest and a new held-out run.

The repository's deterministic tests may verify examples such as adult
evidence at/above the configured hard-block boundary, fail-closed behavior,
and review routing for partial failure. These are policy-contract checks, not
benchmark examples and must not be counted as model performance items.

## Explicit non-claims

- Offline dataset metrics describe agreement with that labelled dataset and
  frozen run only. They do **not** establish real-world effectiveness,
  generalisation, prevalence-weighted risk, or user safety.
- A policy threshold is not a sensitivity, specificity, or accuracy guarantee.
- The quarantine/label audit of restricted adult examples proves isolation and
  expected policy labels only. It is **not an 18+ accuracy result** and must
  not be reported as one.
- No age-estimation or adult-content performance result is claimed until a
  suitable, lawfully usable, independently labelled and held-out evaluation
  set is reviewed.
- External validation is still required: independent annotation review,
  representative held-out data, subgroup/locale analysis, adversarial and
  distribution-shift testing, human-review quality/latency checks, and
  privacy/safety review under the intended deployment conditions.

## Review gate

A run is ready for submission review only when the evidence template is
complete, the export can be rerun to the same JSON result, all exclusions are
explained, and the reviewer can distinguish:

```text
policy contract checks
≠ offline dataset metrics
≠ real-world effectiveness
≠ external validation
```

An unrun benchmark is reported as `NOT RUN`, not as zero and not as a pass.