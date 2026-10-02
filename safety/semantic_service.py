"""Semantic text ranking for LittleNet's personalized For You feed.

This is deliberately separate from the moderation decision path. Candidate posts
are already Kids-Mode-safe, age-appropriate and allowed by Parent Controls before
semantic ranking runs. A model failure therefore falls back to deterministic
ranking and can never make unsafe content visible.
"""
import os

_MODEL=None
_PROCESSOR=None
_DEVICE=None
CLIP_MODEL_ID='openai/clip-vit-base-patch32'
CLIP_REVISION='3d74acf9a28c67741b2f4f2ea7635f0aaf6f0268'


def _load():
    global _MODEL,_PROCESSOR,_DEVICE
    if _MODEL is not None:return _MODEL,_PROCESSOR,_DEVICE
    import torch
    from transformers import CLIPModel,CLIPProcessor
    want=os.getenv('LITTLENET_DEVICE','cpu').lower()
    device='cuda' if want=='cuda' and torch.cuda.is_available() else 'cpu'
    model=CLIPModel.from_pretrained(CLIP_MODEL_ID,revision=CLIP_REVISION).to(device)
    model.eval()
    proc=CLIPProcessor.from_pretrained(CLIP_MODEL_ID,revision=CLIP_REVISION)
    _MODEL,_PROCESSOR,_DEVICE=model,proc,device
    return _MODEL,_PROCESSOR,_DEVICE


def rank_texts(profile_text,texts):
    """Return cosine-like CLIP text similarity scores in input order."""
    texts=[str(x or '')[:500] for x in texts]
    if not texts:return []
    query=(str(profile_text or '').strip() or 'safe educational content for children')[:500]
    model,processor,device=_load()
    import torch
    encoded=processor(text=[query]+texts,return_tensors='pt',padding=True,truncation=True)
    encoded={k:v.to(device) for k,v in encoded.items() if k in {'input_ids','attention_mask'}}
    with torch.inference_mode():
        features=model.get_text_features(**encoded)
        features=features/features.norm(dim=-1,keepdim=True).clamp_min(1e-12)
        scores=(features[1:] @ features[0]).detach().float().cpu().tolist()
    return [float(x) for x in scores]
