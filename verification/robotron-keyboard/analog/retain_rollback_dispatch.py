#!/usr/bin/env python3
"""Retain complete, waveform-verified rollback dispatch evidence."""
import argparse
import json
import lzma
from pathlib import Path
import shutil
from rollback_dispatch_review import review
from ttl7406_probe import sha

HERE=Path(__file__).resolve().parent


def retain(root, baseline, build, out):
    result=review(root,baseline,build)
    if out.exists() and (set(p.name for p in out.iterdir())!={'build.json'} or sha(out/'build.json')!=sha(build)):
        raise ValueError('Refusing to replace retained evidence')
    out.mkdir(parents=True,exist_ok=True)
    if build.resolve()!=(out/'build.json').resolve():shutil.copyfile(build,out/'build.json')
    for name in ('baseline.json','capture-generator.py'):shutil.copyfile(root/name,out/name)
    if json.loads((baseline/'run.json').read_text()).get('rawOutput'):
        (out/'baseline-traces.json').write_text(json.dumps(result['comparisons']['off'],indent=2)+'\n')
    else:
        shutil.copyfile(baseline/'completion-check.json',out/'baseline-traces.json')
    for mode in ('off','on'):
        target=out/mode;target.mkdir()
        for name in ('io.cir','run.json'):shutil.copyfile(root/mode/name,target/name)
        with (root/mode/'ngspice.log').open('rb') as source,lzma.open(target/'ngspice.log.xz','wb',preset=6) as destination:
            shutil.copyfileobj(source,destination,1024*1024)
    result['retention']={'fullCaptures':str(root.resolve()),'scope':'Full compressed waveforms remain local; run receipts pin original bytes. Every sample was checked against the baseline before retention.',
        'sources':{n:sha(HERE/n) for n in ('rollback_dispatch_review.py','rollback_audit_log.py','live_raw_review.py','raw_waveform.py','retain_rollback_dispatch.py','engine-patches/ngspice-47-rollback-audit.patch')}}
    (out/'assessment.json').write_text(json.dumps(result,indent=2)+'\n')
    manifest={str(p.relative_to(out)):sha(p) for p in sorted(out.rglob('*')) if p.is_file()}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('root','baseline','build-receipt'):p.add_argument('--'+name,type=Path)
    p.add_argument('--out',type=Path,required=True);p.add_argument('--check',action='store_true');a=p.parse_args()
    if a.check:
        expected=json.loads((a.out/'manifest.json').read_text())
        actual={str(f.relative_to(a.out)):sha(f) for f in a.out.rglob('*') if f.is_file() and f.name!='manifest.json'}
        if actual!=expected:raise ValueError('Changed retained rollback evidence')
    else:
        if not all((a.root,a.baseline,a.build_receipt)):p.error('Retention requires both captures, baseline and build receipt')
        retain(a.root,a.baseline,a.build_receipt,a.out)
