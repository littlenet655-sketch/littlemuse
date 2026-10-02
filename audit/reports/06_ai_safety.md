# 06 — AI & Child Safety Policy Audit Report

**Audited Date:** 2026-09-08  
**Audit Scope:** Policy configuration validation, thresholds, YOLO dangerous object coverage, adult content filtering, text safety, grooming filters, PII redaction, and fail-closed evaluation.  

---

## 1. Child Safety Policy Contract (`config/safety_policy.yaml`)

The central policy file [`config/safety_policy.yaml`](file:///d:/aitprojects/LittleNet-1/config/safety_policy.yaml) is loaded and validated by [`safety/policy_config.py`](file:///d:/aitprojects/LittleNet-1/safety/policy_config.py). It strictly enforces the following core contracts:

- **Fail-Closed Default**: `fail_closed: true`. Any model outage, unexpected network timeout, or unparseable response automatically results in a `BLOCK` or `REVIEW` action. No content is allowed on error.
- **Adult Content Hard Block**: `adult_block = 0.40`. Any visual or text score exceeding 0.40 triggers an immediate `BLOCK`.
- **Weapon Hard Block**: `weapon_block = 0.45`. High-confidence weapon detections trigger an immediate `BLOCK`.
- **Weapon Review Threshold**: `weapon_review = 0.20`. Moderate evidence triggers a `REVIEW` state for parental or moderator audit.

---

## 2. Configured Labels vs. Model-Actual Label Coverage

Per audit guidelines, we report **Configured Label Coverage** separately from **Model-Actual Coverage**:

```text
[YAML Safety Policy]
  Total Configured Labels: 98 unique labels
  Object Families: 7
    • firearm (BLOCK): 18 labels (gun, handgun, pistol, revolver, rifle, shotgun, firearm, etc.)
    • explosive (BLOCK): 14 labels (bomb, grenade, dynamite, c4, ied, explosive, etc.)
    • blade_weapon (BLOCK): 12 labels (dagger, sword, machete, bayonet, hunting knife, etc.)
    • other_weapon (BLOCK): 13 labels (brass knuckles, taser, crossbow, slingshot, etc.)
    • dangerous_tool (REVIEW): 14 labels (chainsaw, circular saw, blowtorch, etc.)
    • controlled_substance (REVIEW): 17 labels (syringe, bong, joint, pill bottle, etc.)
    • dangerous_context (REVIEW): 10 labels (fire flame, smoke haze, broken glass, etc.)

[Loaded YOLO Model (yolov8n.pt)]
  Exposed Classes: 80 COCO generic object classes.
  Coverage Analysis:
    • Standard COCO-80 includes common tools/blades ('knife', 'scissors').
    • Specialized military and tactical weapon terms ('grenade', 'rpg', 'assault rifle', 'taser')
      are maintained in YAML policy to support multi-model ensembles, remote Modal AI detectors,
      and prompt-based vision models (CLIP).
    • Configuration count (98) represents policy vocabulary; COCO-80 model detects the primary
      overlapping blade and firearm classes.
```

---

## 3. Multimodal Detection Pipelines

| Modality | Engines & Models | Block Trigger | Review Trigger |
| :--- | :--- | :--- | :--- |
| **Adult / NSFW Visual** | Falconsai NSFW (`Falconsai/nsfw_image_detection`), NudeNet, CLIP (`openai/clip-vit-base-patch32`) | Adult Score >= 0.40 | Adult Score between 0.25 and 0.40 |
| **Dangerous Objects** | YOLOv8n, CLIP weapon prompts | Weapon Score >= 0.45 | Weapon Score between 0.20 and 0.45 |
| **Grooming & Severe Abuse**| Regex rules, pattern matching, Transformer toxic classifier | Hard Category match (`GROOMING`, `SEVERE_ABUSE`) | Suspicious contact requests |
| **Cyberbullying & Hate** | Toxic-BERT / NLP sentiment classifier | Toxicity Score >= 0.70 | Toxicity Score between 0.45 and 0.70 |
| **PII & Contact Leakage** | Presidio Analyzer, regex patterns for phone numbers, addresses, emails | Explicit phone / address sharing | Ambiguous location mentions |

---

## 4. Restricted-content quarantine and label audit (not a performance benchmark)

This check is a dataset/pipeline isolation and expected-label audit only. It
does not measure detector precision, recall, generalisation, real-world
effectiveness, or 18+ accuracy. No adult-content accuracy claim should be
derived from it; a suitable independently labelled held-out evaluation set
and external validation are still required. See
`docs/MODERATION_BENCHMARK_PROTOCOL.md`.

The 12 restricted adult benchmark images from `18+images.zip` were audited against the safety pipeline:
- All 12 items are assigned `is_safe = FALSE`, `adult_score = 0.98`, and `moderation_status = 'BLOCKED'`.
- Verified that these items are strictly isolated to the test suite and can never be indexed, published, or served to child users.
