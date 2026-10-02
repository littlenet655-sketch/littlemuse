# 02 — Dataset Validation & Ingestion Blocker Report

**Audited Date:** 2026-09-08  
**Audit Scope:** Full mechanical validation of the 206-item LittleNet dataset, two-part ZIP bundle integrity, and ingestion pipeline behavior.  
**Severity:** **P0 DATASET BLOCKER**  

---

## 1. Expected Dataset Contract vs Actual State

| Metric | Required Contract | Audited Actual | Status |
| :--- | :---: | :---: | :---: |
| **Total Media Items** | **206** | **206** | PASS |
| **Allowed Kid-Safe Items** | **194** | **194** | PASS |
| **Blocked Benchmark Items** | **12** | **12** | PASS |
| **Total Videos** | **127** | **127** | PASS |
| **Total Images** | **79** | **79** | PASS |
| **Vertical Reels (9:16)** | **122** | **122** | PASS |
| **Non-Reel Feed Posts** | **84** | **84** | PASS |
| **Family Category** | **74** | **74** | PASS |
| **Animals Category** | **58** | **58** | PASS |
| **Crafts Category** | **26** | **26** | PASS |
| **Gardening Category** | **21** | **21** | PASS |
| **Cooking Category** | **15** | **15** | PASS |
| **Blocked Benchmark** | **12** | **12** | PASS |
| **Unique Media Byte Payloads** | **206** | **205** (1 duplicate) | **FAIL (P0 BLOCKER)** |

---

## 2. Bundle Packaging & Delivery Integrity

The dataset is packaged into two delivery bundles adhering to the 512 MB platform constraint:

1. **`LittleNet_Dataset_Part1_of_2.zip`**
   - **Path**: `D:\aitprojects\database\LittleNet_Dataset_Part1_of_2.zip`
   - **Size**: 417.62 MB (Under 512 MB: True)
   - **Total Files**: 97 (including `littlenet_dataset_captions.csv`)
   - **Categories**: `18+images/` (12), `Member3Animals/` (58), `Member3Crafts&Hobbies/` (26)

2. **`LittleNet_Dataset_Part2_of_2.zip`**
   - **Path**: `D:\aitprojects\database\LittleNet_Dataset_Part2_of_2.zip`
   - **Size**: 427.34 MB (Under 512 MB: True)
   - **Total Files**: 111 (including `littlenet_dataset_captions.csv`)
   - **Categories**: `family/` (74), `Member3Cooking/` (15), `Member3Gardening/` (21)

---

## 3. The Row 120 Blocker Investigation

### 3.1 Defect Description
- **CSV Row 34 (`Member3Animals`)**: `fun-animal-facts-for-kids.jpg`
  - Dimensions: 1024 x 724
  - SHA-256: `e9821bdd4fd24a00abf2965d542287e7b969704501f1323acb10b62e9672dd56`
  - Metadata: *Fun Animal Facts: Nature's Record Breakers*
  - Visual Reality: Infographic showing wild animal facts.

- **CSV Row 120 (`Member3Gardening`)**: `fun-animal-facts-for-kids.jpg`
  - Dimensions: 1024 x 724
  - SHA-256: `e9821bdd4fd24a00abf2965d542287e7b969704501f1323acb10b62e9672dd56`
  - Metadata: *Garden Friends: Earthworms at Work* (Caption claims earthworms aerating soil).
  - Visual Reality: Byte-identical copy of the animal facts infographic.

### 3.2 Local Source Search & Fix Rule Outcome
An exhaustive search was executed across:
- `D:\aitprojects\`
- `D:\aitprojects\database\`
- `D:\aitprojects\database.zip`
- `C:\Users\aksha\Downloads\`
- Repository source tree

**Result**: Zero matching genuine earthworm/gardening images exist in the supplied local folders.
Per the strict audit rule:
1. Fabricating a synthetic replacement image is **prohibited**.
2. Silently relabeling the duplicate animal image as gardening is **prohibited**.
3. Therefore, this defect remains a confirmed **P0 DATASET BLOCKER**.

---

## 4. Ingestion Dry-Run Execution & Evidence

### Command Executed:
```bash
python -m tools.dataset_bundle_ingest \
  --bundle "D:\aitprojects\database\LittleNet_Dataset_Part1_of_2.zip" \
  --bundle "D:\aitprojects\database\LittleNet_Dataset_Part2_of_2.zip" \
  --dataset-version v1
```

### Execution Result:
```text
Traceback (most recent call last):
  File "D:\aitprojects\LittleNet-1\tools\dataset_bundle_ingest.py", line 160, in stage_bundles
    raise RuntimeError(f"duplicate media bytes detected: {prior!r} and {filename!r}")
RuntimeError: duplicate media bytes detected: 'fun-animal-facts-for-kids.jpg' and 'fun-animal-facts-for-kids.jpg'
```

### Safety Assessment:
The staging adapter `tools.dataset_bundle_ingest` operated in full **fail-closed** mode. It identified the duplicate SHA-256 payload and aborted before mutating database records or staging corrupted catalog entries.

---

## 5. Remediation Plan (Required for Release)

1. Obtain the genuine source image for *Garden Friends: Earthworms at Work* from the original content author.
2. Replace `Member3Gardening/fun-animal-facts-for-kids.jpg` with the genuine file (e.g. `earthworms-in-garden.jpg`).
3. Update Row 120 in `littlenet_dataset_captions.csv` with the new filename, file size, dimensions, and SHA-256 hash.
4. Repackage `LittleNet_Dataset_Part2_of_2.zip`.
5. Re-run `python -m tools.dataset_bundle_ingest` in dry-run mode to verify all 206 payloads pass uniqueness checks.
