"""Run one local file/text through the exact LittleNet moderation adapters."""
import argparse,json
from safety.moderation_service import evaluate

def main():
    p=argparse.ArgumentParser();p.add_argument('modality',choices=['TEXT','IMAGE','VIDEO','AUDIO']);p.add_argument('value');p.add_argument('--child-id',type=int,default=0);a=p.parse_args()
    signals,decision=evaluate(a.child_id,a.modality,a.value)
    print(json.dumps({'signals':signals,'decision':decision.__dict__},indent=2,default=str))
    if a.modality in {'IMAGE','VIDEO','AUDIO'} and (signals.get('total_safety_failure') or signals.get('partial_safety_failure')):
        print('\nNOTE: one or more safety engines were unavailable; LittleNet did not silently allow the item.')
if __name__=='__main__':main()
