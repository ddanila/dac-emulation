#!/usr/bin/env python3
"""Require actual board bus execution after the second unsupported-class refusal."""
import argparse,json
from pathlib import Path
from parameter_late_refusal_review import review as full_review
from parameter_continue_activity import activity
from ttl7406_probe import sha


def review(root):
    result=full_review(root)
    if json.loads(json.dumps(result))!=json.loads((root/'assessment.json').read_text()):raise ValueError('Changed complete refusal review')
    found={}
    for mode,state in result['negativeControls'].items():
        target=state['fault']['laterRefusalSeconds']
        found[mode]=activity(root/mode/'ngspice.log',target)
        if found[mode]!=activity(root/'baseline/ngspice.log',target):raise ValueError('Changed post-refusal bus activity')
    return dict(qualified=False,completeReviewSha256=sha(root/'assessment.json'),postRefusalActivity=found,
                scope='Full refusal review replayed. Nonempty bus activity after the second refusal matches the original board reference for all three native parameter families. This establishes ordinary execution after refusal, not observable private state for the unsupported object.')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();result=review(a.root)
    with a.out.open('x') as f:json.dump(result,f,indent=2);f.write('\n')
