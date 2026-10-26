#!/usr/bin/env python3
"""Capture interactions between startup fixes without resuming full-repeat work."""
import argparse
import json
from pathlib import Path
import output_history_capture as engine
from ttl7406_probe import sha
VARIANTS={
    'off':{'ROBOTRON_HISTORY_INIT':'off','ROBOTRON_STAGED_OUTPUT':'off'},
    'history':{'ROBOTRON_HISTORY_INIT':'on','ROBOTRON_STAGED_OUTPUT':'off'},
    'staged':{'ROBOTRON_HISTORY_INIT':'off','ROBOTRON_STAGED_OUTPUT':'on'},
    'combined':{'ROBOTRON_HISTORY_INIT':'on','ROBOTRON_STAGED_OUTPUT':'on'},
    'combined-zero':{'ROBOTRON_HISTORY_INIT':'on','ROBOTRON_STAGED_OUTPUT':'on','ROBOTRON_HISTORY_SEED':'zero'},
    'combined-one':{'ROBOTRON_HISTORY_INIT':'on','ROBOTRON_STAGED_OUTPUT':'on','ROBOTRON_HISTORY_SEED':'one'},
}
for environment in VARIANTS.values():environment['ROBOTRON_HISTORY_STATE']='off'


def run(a):
    controller=sha(Path(__file__));previous=engine.VARIANTS
    try:
        engine.VARIANTS=VARIANTS
        engine.run(a.source,a.models,a.runtime,a.out)
    finally:engine.VARIANTS=previous
    for mode in VARIANTS:
        path=a.out/mode/'run.json';receipt=json.loads(path.read_text())
        receipt['variantControllerSha256']=controller
        path.write_text(json.dumps(receipt,indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('source','models','runtime','out'):p.add_argument('--'+name,type=Path,required=True)
    run(p.parse_args())
