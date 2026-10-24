#!/usr/bin/env python3
"""Retain a complete paired retry assessment without duplicating raw waveforms."""
import argparse
import json
import lzma
from pathlib import Path
import shutil
from bridge_rollback_log import analyze as bridge_analyze
from newton_retry_review import review
from rollback_audit_log import analyze as dispatch_analyze
from trace_io import open_binary, open_text
from ttl7406_probe import sha

HERE=Path(__file__).resolve().parent


def check(out):
    expected=json.loads((out/'manifest.json').read_text())
    actual={str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.is_file() and p.name!='manifest.json'}
    if actual!=expected:raise ValueError('Changed retained retry evidence')
    assessment=json.loads((out/'assessment.json').read_text())
    end=assessment['disabledControl']['endSeconds']
    with open_text(out/'on/ngspice.log') as stream:
        if dispatch_analyze(stream)!=assessment['dispatch']:raise ValueError('Changed dispatch interpretation')
    with open_text(out/'on/ngspice.log') as stream:
        if bridge_analyze(stream,expected_end=end)!=assessment['timing']:raise ValueError('Changed HDL timing interpretation')


def retain(root,control,evidence,out):
    result=review(root,control,evidence)
    out.mkdir(parents=True,exist_ok=False)
    for name in ('build.json','capture-generator.py'):shutil.copyfile(root/name,out/name)
    shutil.copyfile(control/'run.json',out/'control.json')
    for mode in ('off','on'):
        target=out/mode;target.mkdir()
        for name in ('run.json','io.cir','bridge.json'):shutil.copyfile(root/mode/name,target/name)
        with open_binary(root/mode/'ngspice.log') as source,lzma.open(target/'ngspice.log.xz','wb') as dest:
            shutil.copyfileobj(source,dest,1024*1024)
    result['retention']={'fullCaptures':str(root.resolve()),
        'scope':'Complete compressed waveforms remain local, pinned by run receipts and compared before retention.',
        'sources':{name:sha(HERE/name) for name in ('newton_retry_review.py','raw_pair_review.py',
            'rollback_audit_log.py','bridge_rollback_log.py','retain_newton_retry.py',
            'engine-patches/rollback_fault.h','engine-patches/ngspice-47-rollback-fault.patch')}}
    (out/'assessment.json').write_text(json.dumps(result,indent=2)+'\n')
    manifest={str(p.relative_to(out)):sha(p) for p in sorted(out.rglob('*')) if p.is_file()}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    check(out)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('root','control','evidence'):p.add_argument('--'+name,type=Path)
    p.add_argument('--out',type=Path,required=True);p.add_argument('--check',action='store_true')
    a=p.parse_args()
    if a.check:check(a.out)
    else:
        if not all((a.root,a.control,a.evidence)):p.error('Retention requires complete pair and established control')
        retain(a.root,a.control,a.evidence,a.out)
