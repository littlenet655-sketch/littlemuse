"""Load each planned pretrained model once and print an honest readiness table."""
import argparse, tempfile, os
from pathlib import Path

def check(name,fn):
    try:
        fn();print(f'[OK]   {name}');return True
    except Exception as e:
        print(f'[FAIL] {name}: {type(e).__name__}: {e}');return False

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--image');ap.add_argument('--audio');args=ap.parse_args()
    results=[]
    results.append(check('Detoxify',lambda: __import__('detoxify').Detoxify('original')))
    results.append(check('NudeNet',lambda: __import__('nudenet').NudeDetector()))
    def clip():
        from transformers import CLIPModel,CLIPProcessor
        CLIPModel.from_pretrained('openai/clip-vit-base-patch32');CLIPProcessor.from_pretrained('openai/clip-vit-base-patch32')
    results.append(check('CLIP',clip))
    def nsfw():
        from transformers import pipeline
        pipeline('image-classification',model='Falconsai/nsfw_image_detection')
    results.append(check('Falconsai NSFW',nsfw))
    print(f'\nREADY {sum(results)}/{len(results)} models')
    raise SystemExit(0 if all(results) else 2)
if __name__=='__main__':main()
