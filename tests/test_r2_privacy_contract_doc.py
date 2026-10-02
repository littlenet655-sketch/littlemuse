from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def test_r2_privacy_contract_mentions_private_signed_no_store_delete():
    text=(ROOT/'docs/R2_MEDIA_PRIVACY_CONTRACT.md').read_text(encoding='utf-8')
    for phrase in ['private Cloudflare R2 bucket','presigned R2 GET URL','private, no-store','successful child post/story deletion']:
        assert phrase in text
