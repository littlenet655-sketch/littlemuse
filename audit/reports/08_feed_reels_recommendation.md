# 08 — Feed, Reels & Recommendation Engine Audit Report

**Audited Date:** 2026-09-08  
**Audit Scope:** Feed algorithms, reels candidate selection, recommendation ranking, category diversity, age gating, parent controls, and curated-social merge status.  

---

## 1. Feature Status Matrix: Implemented vs. Missing

| Feature Requirement | Status | Implementation Location | Audit Evaluation |
| :--- | :---: | :--- | :--- |
| **Safety-Before-Ranking Gate** | **IMPLEMENTED** | `services/recommendation.py:24` | Filters `p.moderation_status='ALLOWED' AND p.is_safe=TRUE` before scoring. |
| **Parent Category Controls** | **IMPLEMENTED** | `services/controls.py:effective_categories` | Respects parental allowlist / blocklist of topic categories. |
| **Child Age Gating** | **IMPLEMENTED** | `services/recommendation.py:24` | Filters `audience_age_group = 'ALL' OR audience_age_group = child_group`. |
| **Category Diversity Enforcement** | **IMPLEMENTED** | `services/recommendation.py:apply_diversity_and_balance` | Enforces `max_consecutive = 2` to prevent single-category content bursts. |
| **Educational Boost** | **IMPLEMENTED** | `services/recommendation.py:60` | Prioritizes Science, Math, Nature, Books, Coding, and General Knowledge. |
| **Blocked Content Leakage Prevention**| **IMPLEMENTED** | DB Queries & R2 signed URL handlers | Blocked, quarantined, or review-pending posts cannot appear in feeds or reels. |
| **Curated Candidate Generator** | **MISSING** | `services/recommendation.py` | `curated_content` tables exist, but runtime queries currently only sample `posts`. |
| **Social + Curated Feed Merge** | **MISSING** | `mobile/api.py:feed` | Does not yet combine child social posts with system curated media. |
| **Empty-Graph Curated Fallback** | **MISSING** | `mobile/api.py:feed` | If a new child has 0 social connections, feed does not auto-populate from curated catalog. |
| **Feed Session Cursor Caching** | **PARTIAL** | Migration `20260908195500` | Tables `feed_sessions` & `feed_session_items` exist; API uses timestamp cursor. |

---

## 2. Recommendation Logic Walkthrough

[`services/recommendation.py`](file:///d:/aitprojects/LittleNet-1/services/recommendation.py) implements personalized ranking:

1. **Candidate Selection**: Samples up to 60 posts matching the viewer's discoverability scope, age group, and allowed parent categories.
2. **Profile Terms Extraction**: Extracts approved skills, interests, and ambitions from `child_skills`, `child_interests`, and `child_ambitions`.
3. **Semantic Scoring**:
   - If Modal AI or local semantic service is enabled, ranks posts using text embeddings against the child's profile summary.
   - If AI service times out or is offline, gracefully falls back to deterministic heuristic scoring (keyword matching + educational category boost + like weighting).
4. **Diversity Re-ordering**:
   - `apply_diversity_and_balance()` iterates through candidates and ensures no more than 2 consecutive posts belong to the same category.
   - Spaces out leisure/entertainment posts by injecting educational posts.

---

## 3. V2 Target Architecture for Curated Content

To complete the V2 rebuild, `services/recommendation.py` must be upgraded to:
1. Query `curated_content` for published, safe, age-appropriate items matching parent controls.
2. Merge curated candidates with child social posts.
3. Fall back 100% to the curated catalog when a new child user has an empty social graph.
