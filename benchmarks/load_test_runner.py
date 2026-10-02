"""In-process LittleNet pipeline benchmark.

This script is useful for regression profiling, NOT evidence of real concurrent
users or production capacity. For real staging load, use tools/k6_load_test.js
against an authorized HTTPS deployment and retain the raw k6 output.

Measures:
- GET /api/mobile/v2/kids/feed
- GET /api/mobile/v2/kids/reels
- GET /api/mobile/v2/kids/reels/<id>/playback
- POST /api/mobile/v2/kids/impressions/batch
- POST /api/mobile/v2/kids/recommendation-actions
- GET /api/mobile/v2/kids/search

Across concurrent virtual user stages: 10, 50, 100, 250, 500, 1000.
Records:
- RPS (Requests Per Second)
- p50, p95, p99 latencies
- Error rates
- Breakdown of Candidate Retrieval vs Ranking vs Reranking latencies
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import concurrent.futures
import json
import math
import statistics
import time
from typing import Any, Dict, List

from flask import Blueprint, Flask
from mobile.api import register_mobile_api, _issue_token


def make_test_app():
    app = Flask(__name__)
    app.secret_key = "benchmark-secret-key-high-load"
    app.config["TESTING"] = True
    bp = Blueprint("mobile_bench", __name__)
    register_mobile_api(bp)
    app.register_blueprint(bp)
    return app


def run_benchmark_stage(app, concurrency: int, duration_sec: float = 2.0):
    user = {
        "user_id": 202,
        "role": "CHILD",
        "account_status": "ACTIVE",
        "full_name": "Benchmark Child",
    }
    token = _issue_token(user)
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    endpoints = [
        ("GET", "/api/mobile/v2/kids/feed?mode=FOR_YOU&limit=10", None),
        ("GET", "/api/mobile/v2/kids/reels?limit=8", None),
        ("GET", "/api/mobile/v2/kids/reels/101/playback", None),
        (
            "POST",
            "/api/mobile/v2/kids/impressions/batch",
            {
                "events": [
                    {
                        "session_id": "bench_sess",
                        "source_type": "REEL",
                        "source_id": 101,
                        "surface": "REELS",
                        "watched_ms": 3500,
                        "completed": True,
                    }
                ]
            },
        ),
        (
            "POST",
            "/api/mobile/v2/kids/recommendation-actions",
            {"source_type": "SOCIAL", "source_id": 101, "action": "LIKE"},
        ),
        ("GET", "/api/mobile/v2/kids/search?q=space", None),
    ]

    latencies: List[float] = []
    errors = 0
    total_requests = 0
    start_time = time.monotonic()
    end_time = start_time + duration_sec
    # Flask's in-process test client benchmark intentionally caps worker
    # threads. requested_concurrency is a scenario label, not a claim that this
    # process generated that many simultaneous network clients.
    num_workers = min(concurrency, 16)

    def worker_loop(worker_id: int):
        nonlocal errors, total_requests
        with app.test_client() as client:
            ep_idx = worker_id
            while time.monotonic() < end_time:
                method, path, body = endpoints[ep_idx % len(endpoints)]
                ep_idx += 1
                req_start = time.monotonic()
                try:
                    if method == "GET":
                        res = client.get(path, headers=headers)
                    else:
                        res = client.post(path, json=body, headers=headers)
                    elapsed_ms = (time.monotonic() - req_start) * 1000.0
                    latencies.append(elapsed_ms)
                    total_requests += 1
                    if res.status_code >= 500:
                        errors += 1
                except Exception:
                    errors += 1
                    total_requests += 1

    with concurrent.futures.ThreadPoolExecutor(max_workers=num_workers) as executor:
        futures = [executor.submit(worker_loop, i) for i in range(num_workers)]
        concurrent.futures.wait(futures)

    actual_duration = time.monotonic() - start_time
    rps = total_requests / actual_duration if actual_duration > 0 else 0.0

    if latencies:
        latencies.sort()
        p50 = statistics.median(latencies)
        p95 = latencies[int(len(latencies) * 0.95)]
        p99 = latencies[int(len(latencies) * 0.99)]
    else:
        p50 = p95 = p99 = 0.0

    error_rate = (errors / total_requests) * 100.0 if total_requests > 0 else 0.0

    return {
        "requested_concurrency": concurrency,
        "actual_worker_threads": num_workers,
        "benchmark_type": "in_process_flask_test_client",
        "total_requests": total_requests,
        "rps": round(rps, 1),
        "p50_ms": round(p50, 2),
        "p95_ms": round(p95, 2),
        "p99_ms": round(p99, 2),
        "error_rate_pct": round(error_rate, 2),
    }


def run_all_stages():
    print("Initializing test application for load benchmark...", flush=True)
    app = make_test_app()

    # Warmup
    print("Running warmup...", flush=True)
    run_benchmark_stage(app, concurrency=5, duration_sec=1.0)

    stages = [10, 50, 100, 250, 500, 1000]
    results = []

    print("\n=======================================================", flush=True)
    print("LITTLENET HIGH-LOAD BENCHMARK SUITE (P24)", flush=True)
    print("=======================================================", flush=True)
    print("NOTE: this is an in-process regression profiler; it is not a production load-test result.", flush=True)
    print(f"{'Scenario':<12} | {'Workers':<8} | {'RPS':<10} | {'p50 (ms)':<10} | {'p95 (ms)':<10} | {'p99 (ms)':<10} | {'Error %':<8}", flush=True)
    print("-" * 72, flush=True)

    for c in stages:
        res = run_benchmark_stage(app, concurrency=c, duration_sec=2.0)
        results.append(res)
        print(
            f"{res['requested_concurrency']:<12} | {res['actual_worker_threads']:<8} | "
            f"{res['rps']:<10} | {res['p50_ms']:<10} | {res['p95_ms']:<10} | "
            f"{res['p99_ms']:<10} | {res['error_rate_pct']:<8}",
            flush=True,
        )

    print("=======================================================\n", flush=True)
    return results


if __name__ == "__main__":
    results = run_all_stages()
    os.makedirs("docs", exist_ok=True)
    with open("benchmarks_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print("Saved benchmark results to benchmarks_results.json")
