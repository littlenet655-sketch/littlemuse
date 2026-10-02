# Row 120 Dataset Replacement Provenance Documentation

**Target Dataset:** LittleNet Curated Multimedia Dataset  
**Record ID:** 120  
**Archive File:** `Member3Gardening.zip`  
**Raw Category:** `Member3Gardening`  
**App Category:** `Science` (Science & Gardening)  
**Title:** `Garden Friends: Earthworms at Work`  
**Date of Replacement:** 2026-09-08  
**Audit Context:** College Project Submission Audit Remediation (FINDING-001)

---

## 1. Issue Addressed

In the original dataset assembly, Row 34 (`Member3Animals/fun-animal-facts-for-kids.jpg`) and Row 120 (`Member3Gardening/fun-animal-facts-for-kids.jpg`) contained the exact identical SHA-256 binary payload (`e9821bdd4fd24a00abf2965d542287e7b969704501f1323acb10b62e9672dd56`).

While Row 34 represented *"Fun Animal Facts: Nature's Record Breakers"*, Row 120 was titled *"Garden Friends: Earthworms at Work"*, with the educational caption:
> *"Earthworms are the soil's secret helpers! By tunneling underground, they aerate the dirt and turn fallen leaves into rich vermicompost fertilizer."*

Exhaustive search of local drives and original collection folders confirmed that the genuine earthworm image was missing and had been duplicated by mistake. Per pre-deployment audit rules, AI generation was strictly prohibited.

---

## 2. Replacement Asset Provenance

A genuine, authentic, and legally reusable educational photograph of an earthworm active in gardening soil was retrieved from Wikimedia Commons:

- **Subject:** *Lumbricus rubellus* (red earthworm / composting worm) in garden soil from organic gardening
- **Source Page:** [https://commons.wikimedia.org/wiki/File:Lumbricus_rubellus_HC1.jpg](https://commons.wikimedia.org/wiki/File:Lumbricus_rubellus_HC1.jpg)
- **Direct Image URL:** [https://upload.wikimedia.org/wikipedia/commons/9/96/Lumbricus_rubellus_HC1.jpg](https://upload.wikimedia.org/wikipedia/commons/9/96/Lumbricus_rubellus_HC1.jpg)
- **Author / Creator:** Holger Casselmann (User:Holger Casselmann on Wikimedia Commons)
- **Date of Creation:** 2011-09-18
- **Retrieval Date:** 2026-09-08
- **License:** Creative Commons Attribution-Share Alike 3.0 Unported ([CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/))
- **File Format:** JPEG (image/jpeg)
- **Pixel Dimensions:** 2500 x 1667 (Width x Height)
- **Aspect Ratio:** ~1.5:1 (Horizontal landscape / Non-reel)
- **File Size (Bytes):** 3,767,912 bytes (3679.6 KB)
- **SHA-256 Digest:** `4f3082b4d4527c0d30e5926d2e79e8c6149b86b41b6faf5eccd03ddd64cb19e9`

---

## 3. Metadata Mapping & Schema Verification

Row 120 in `littlenet_dataset_captions.csv` has been updated with the following verified values:

| Field | Value |
|---|---|
| `id` | `120` |
| `archive_file` | `Member3Gardening.zip` |
| `raw_category` | `Member3Gardening` |
| `app_category` | `Science` |
| `filename` | `garden-friends-earthworms-at-work.jpg` |
| `media_type` | `IMAGE` |
| `is_reel` | `False` |
| `is_story` | `False` |
| `width` | `2500` |
| `height` | `1667` |
| `resolution` | `2500x1667` |
| `duration_seconds` | *(empty string)* |
| `file_size_bytes` | `3767912` |
| `file_size_kb` | `3679.6` |
| `title` | `Garden Friends: Earthworms at Work` |
| `caption` | `Earthworms are the soil's secret helpers! By tunneling underground, they aerate the dirt and turn fallen leaves into rich vermicompost fertilizer.` |
| `hashtags` | `#Earthworms #SoilHealth #Vermicompost #UndergroundEcology #NatureHelpers` |
| `audience_age_group` | `ALL` |
| `is_safe` | `True` |
| `moderation_status` | `ALLOWED` |
| `safety_score` | `0.99` |
| `adult_score` | `0.01` |
| `app_destination_tab` | `Community Feed (Nature & Science)` |
| `safety_reason` | `Verified kid-safe gardening, biology & science content` |

---

## 4. Contract Integrity

The full LittleNet dataset contract is preserved:
- **Total Media Items:** 206
- **ALLOWED:** 194
- **BLOCKED:** 12
- **VIDEO:** 127
- **IMAGE:** 79
- **REELS:** 122
- **NON-REELS:** 84
- **Unique Media Payloads:** 206 unique SHA-256 digests across all files. Zero byte collisions.
