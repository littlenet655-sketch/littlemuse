"""Profiler for recommendation pipeline stages:
1. Candidate Retrieval (Social + Curated)
2. Recommendation Ranking (Deterministic + Feedback Scoring)
3. Diversity & Repetition Reranking
4. Database / pgvector query latency
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import time
from typing import Any, Dict, List
from database.connection import fetch_all, fetch_one
from services.curated_feed import apply_category_diversity
from services.recommendation import candidates, rank_candidates


def profile_recommendation_pipeline(child_id: int = 202, cap: int = 60) -> Dict[str, Any]:
    # Stage 1: Candidate Retrieval
    t0 = time.monotonic()
    retrieved = candidates(child_id, cap=cap, surface="REELS")
    t1 = time.monotonic()
    candidate_retrieval_ms = (t1 - t0) * 1000.0

    # Synthetic candidates combined for stage 2
    items = retrieved if retrieved else [
        {
            "source_type": "CURATED",
            "source_id": i,
            "content_id": i,
            "category": "science" if i % 2 == 0 else "art",
            "is_educational": True,
            "quality_score": 0.85,
            "created_at": "2026-09-19T00:00:00Z",
        }
        for i in range(1, 41)
    ]

    # Stage 2: Ranking
    t2 = time.monotonic()
    ranked = rank_candidates(child_id, items)
    t3 = time.monotonic()
    ranking_ms = (t3 - t2) * 1000.0

    # Stage 3: Diversity & Repetition Reranking
    t4 = time.monotonic()
    diversified = apply_category_diversity(ranked, max_consecutive=2)
    t5 = time.monotonic()
    reranking_ms = (t5 - t4) * 1000.0

    total_pipeline_ms = candidate_retrieval_ms + ranking_ms + reranking_ms

    # Check pgvector index query
    pgvector_query_ms = 0.0
    try:
        t6 = time.monotonic()
        # Test vector distance query if embeddings table exists
        sample_vec = "[" + ",".join(["0.01"] * 384) + "]"
        rows = fetch_all(
            """SELECT media_id, 1 - (embedding <=> %s::vector) AS similarity 
               FROM item_embeddings 
               ORDER BY embedding <=> %s::vector 
               LIMIT 10""",
            (sample_vec, sample_vec),
        )
        t7 = time.monotonic()
        pgvector_query_ms = (t7 - t6) * 1000.0
    except Exception:
        pgvector_query_ms = -1.0  # Table or extension unseeded

    return {
        "candidate_count": len(items),
        "candidate_retrieval_ms": round(candidate_retrieval_ms, 2),
        "ranking_ms": round(ranking_ms, 2),
        "reranking_ms": round(reranking_ms, 2),
        "total_pipeline_ms": round(total_pipeline_ms, 2),
        "pgvector_query_ms": round(pgvector_query_ms, 2) if pgvector_query_ms >= 0 else "N/A (unseeded)",
    }


if __name__ == "__main__":
    profile = profile_recommendation_pipeline()
    print("Pipeline Profiling Results:")
    for k, v in profile.items():
        print(f"  {k}: {v}")
