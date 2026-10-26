#!/usr/bin/env python3
"""Capture matched output-breakpoint controls in the bounded observer fixture."""
import argparse,json,re
from pathlib import Path
import output_history_capture as engine
from ttl7406_probe import sha
VARIANTS={mode:{'ROBOTRON_OUTPUT_BREAKPOINT':mode,'ROBOTRON_HISTORY_INIT':'on',
                'ROBOTRON_STAGED_OUTPUT':'on','ROBOTRON_HISTORY_STATE':'off'}
          for mode in ('off','observe','fail-once')}


def run(a):
    prior=json.loads((a.source/'run.json').read_text());deck=(a.source/'io.cir').read_text()
    if prior['exitCode']!=0:raise ValueError('Need completed source control')
    models=re.findall(r'^\.model\s+(\S+)\s+d_cosim\b',deck,re.M|re.I)
    if len(models)!=1 or len(re.findall(r'^A\S+\s+[^\n]+\s'+re.escape(models[0])+r'\s*$',deck,re.M|re.I))!=1:
        raise ValueError('Probe requires one co-simulation instance')
    previous=engine.VARIANTS;digest=sha(Path(__file__))
    try:
        engine.VARIANTS=VARIANTS;engine.run(a.source,a.models,a.runtime,a.out)
    finally:engine.VARIANTS=previous
    for mode in VARIANTS:
        p=a.out/mode/'run.json';r=json.loads(p.read_text())
        r['variantControllerSha256']=digest;r['qualified']=False
        r['scope']='Complete 20-us diagnostic fixture; an artificial failed breakpoint is not a physical failure or recovery qualification.'
        p.write_text(json.dumps(r,indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('source','models','runtime','out'):p.add_argument('--'+name,type=Path,required=True)
    run(p.parse_args())
