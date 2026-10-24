#!/usr/bin/env python3
"""Retain a verified full-scenario comparison while leaving raw waveforms local."""
import argparse
import json
import lzma
from pathlib import Path
import shutil
from full_scenario_refinement import review,same_events
from trace_io import open_binary
from ttl7406_probe import sha

HERE=Path(__file__).resolve().parent
LABELS=('coarse','middle','fine')


def check(out):
    expected=json.loads((out/'manifest.json').read_text())
    actual={str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.is_file() and p.name!='manifest.json'}
    if actual!=expected:raise ValueError('Changed retained scenario evidence')
    result=json.loads((out/'assessment.json').read_text())
    count=same_events([out/label/'ngspice.log' for label in LABELS])
    if count!=result['firmwareEventRecordsCompared']:raise ValueError('Changed retained firmware observations')


def retain(directories,out):
    result=review(directories)
    for root in directories:
        receipt=json.loads((root/'run.json').read_text())
        if sha(root/'capture-generator.py')!=receipt['generatorSha256']:
            raise ValueError('Missing or changed capture generator')
    out.mkdir(parents=True,exist_ok=False)
    for label,root in zip(LABELS,directories):
        target=out/label;target.mkdir()
        for name in ('run.json','io.cir','scenario.json','capture-generator.py'):
            shutil.copyfile(root/name,target/name)
        if (root/'sampling-grid.json').exists():shutil.copyfile(root/'sampling-grid.json',target/'sampling-grid.json')
        with open_binary(root/'ngspice.log') as source,lzma.open(target/'ngspice.log.xz','wb') as dest:
            shutil.copyfileobj(source,dest,1024*1024)
    result['retention']={'fullCaptures':{label:str(root.resolve()) for label,root in zip(LABELS,directories)},
        'scope':'Complete raw waveforms remain local, pinned in receipts and checked before retention. Manifest checks do not rerun waveform comparison.',
        'sources':{name:sha(HERE/name) for name in ('full_scenario_refinement.py','full_scenario_review.py',
            'scenario_capture.py','raw_pair_review.py','raw_waveform.py','retain_full_scenario.py')}}
    (out/'assessment.json').write_text(json.dumps(result,indent=2)+'\n')
    manifest={str(p.relative_to(out)):sha(p) for p in sorted(out.rglob('*')) if p.is_file()}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    check(out)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('runs',nargs='*',type=Path);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--check',action='store_true');a=p.parse_args()
    if a.check:check(a.out)
    else:
        if len(a.runs)!=3:p.error('Retention requires three complete captures')
        retain(a.runs,a.out)
