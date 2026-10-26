#!/usr/bin/env python3
"""Compose the opt-in history initializer and repeated-output fix."""
import argparse
import json
from pathlib import Path
import build_staged_output as staged
import build_output_history_init as history
from ttl7406_probe import sha
BASE_INSTRUMENT=staged.instrument


def instrument(text,fixture):
    initialized,_=history.instrument(text,fixture)
    return BASE_INSTRUMENT(initialized,fixture)


def run(a):
    original=staged.instrument
    try:
        staged.instrument=instrument
        staged.run(a)
    finally:staged.instrument=original
    path=a.out/'build.json';receipt=json.loads(path.read_text())
    for p in (Path(__file__),Path(history.__file__)):
        receipt['sources'][str(p.resolve())]=sha(p)
    receipt['scope']='Independent opt-in history initialization and repeated-output staging fixes in one model. No full startup, repeat or board qualification.'
    path.write_text(json.dumps(receipt,indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('base','ngspice-source','ngspice-build','vpi-include','out'):p.add_argument('--'+name,type=Path,required=True)
    run(p.parse_args())
