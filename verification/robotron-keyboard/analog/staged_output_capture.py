#!/usr/bin/env python3
"""Use the bounded capture engine with explicit staged-output variants."""
import argparse
import json
from pathlib import Path
import output_history_capture as capture_engine
from ttl7406_probe import sha
VARIANTS={'off':{'ROBOTRON_STAGED_OUTPUT':'off','ROBOTRON_HISTORY_STATE':'off'},
          'observe':{'ROBOTRON_STAGED_OUTPUT':'off','ROBOTRON_HISTORY_STATE':'check'},
          'fixed':{'ROBOTRON_STAGED_OUTPUT':'on','ROBOTRON_HISTORY_STATE':'off'},
          'fixed-observe':{'ROBOTRON_STAGED_OUTPUT':'on','ROBOTRON_HISTORY_STATE':'check'}}


def run(a):
    controller=sha(Path(__file__));previous=capture_engine.VARIANTS
    try:
        capture_engine.VARIANTS=VARIANTS
        capture_engine.run(a.source,a.models,a.runtime,a.out)
    finally:capture_engine.VARIANTS=previous
    for mode in VARIANTS:
        path=a.out/mode/'run.json';r=json.loads(path.read_text());r['variantControllerSha256']=controller
        path.write_text(json.dumps(r,indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('source','models','runtime','out'):p.add_argument('--'+name,type=Path,required=True)
    run(p.parse_args())
