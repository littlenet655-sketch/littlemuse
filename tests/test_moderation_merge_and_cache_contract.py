import ast
import os
import pytest
from database.connection import execute, fetch_one
from services.moderation_cache import get_cached_signals, store_cached_signals, text_fingerprint
from safety.policy import decide


def test_mobile_api_merge_signals_delegates_structurally():
    txt = open('mobile/api.py', 'r', encoding='utf-8').read()
    tree = ast.parse(txt)
    found_delegate = False
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == '_merge_signals':
            for subnode in ast.walk(node):
                if isinstance(subnode, ast.ImportFrom) and subnode.module == 'services.media_processor':
                    for alias in subnode.names:
                        if alias.name == '_merge_signals':
                            found_delegate = True
    assert found_delegate, 'mobile/api._merge_signals must delegate to services.media_processor._merge_signals'


def test_moderation_cache_fail_closed_and_policy_reapplied():
    if not os.environ.get('DATABASE_URL'):
        pytest.skip('No DATABASE_URL configured')

    import uuid; fp = text_fingerprint(f'unit_test_unique_content_{uuid.uuid4().hex}')
    
    # 1. Media failure never cached as safe
    failed_signal = {
        'category': 'TEXT',
        'adult_score': 0.0,
        'total_safety_failure': True,
    }
    stored = store_cached_signals('TEXT', fp, failed_signal)
    assert stored is False
    assert get_cached_signals('TEXT', fp) is None

    # 2. Clean signal cached, retrieved, policy reapplied
    clean_signal = {
        'category': 'TEXT',
        'adult_score': 0.05,
        'toxicity_score': 0.02,
        'risk_score': 0.05,
        'partial_safety_failure': False,
        'total_safety_failure': False,
    }
    stored = store_cached_signals('TEXT', fp, clean_signal)
    assert stored is True

    retrieved = get_cached_signals('TEXT', fp)
    assert retrieved is not None
    assert retrieved['adult_score'] == 0.05
    assert retrieved.get('cache', {}).get('hit') is True

    # 3. Policy is reapplied on hit (signals do not contain final ALLLOW/BLOCK decision)
    assert 'action' not in retrieved
    decision = decide(retrieved, 'STRICT')
    assert decision.action == 'ALLOW'
