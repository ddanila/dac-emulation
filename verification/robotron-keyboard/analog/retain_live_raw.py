#!/usr/bin/env python3
"""Retain checked live transport receipts; full compressed captures remain local."""
import argparse
import json
import lzma
from pathlib import Path
import shutil
from live_raw_review import review
from ttl7406_probe import sha

HERE=Path(__file__).resolve().parent


def retain(root, baseline, out):
    assessment=review(root,baseline)
    build=HERE/'reports/raw-pipe-transport/build.json'
    provenance=json.loads(build.read_text())
    run=json.loads((root/'pipe/run.json').read_text())
    if run['runtime']['executable']['sha256']!=provenance['runtimeSha256']:
        raise ValueError('Different diagnostic runtime')
    out.mkdir(parents=True,exist_ok=False)
    for name in ('baseline.json','capture-generator.py'):
        shutil.copyfile(root/name,out/name)
    shutil.copyfile(build,out/'build.json')
    shutil.copyfile(baseline/'completion-check.json',out/'baseline-traces.json')
    for label in ('memory','pipe'):
        target=out/label;target.mkdir()
        for name in ('io.cir','run.json'):
            shutil.copyfile(root/label/name,target/name)
        data=(root/label/'ngspice.log').read_bytes()
        (target/'ngspice.log.xz').write_bytes(lzma.compress(data,preset=6))
    assessment['retention']={'fullCaptures':str(root.resolve()),
        'scope':'Complete compressed waveforms remain at the capture path. Run receipts pin their original byte hashes; every sample was compared before retention.',
        'sources':{name:sha(HERE/name) for name in ('live_raw_review.py','raw_waveform.py','retain_live_raw.py','compressed_output.py','engine-patches/ngspice-47-raw-pipe.patch')}}
    (out/'assessment.json').write_text(json.dumps(assessment,indent=2)+'\n')
    manifest={str(p.relative_to(out)):sha(p) for p in sorted(out.rglob('*')) if p.is_file()}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path)
    p.add_argument('--baseline',type=Path)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--check',action='store_true')
    a=p.parse_args()
    if a.check:
        expected=json.loads((a.out/'manifest.json').read_text())
        actual={str(f.relative_to(a.out)):sha(f) for f in a.out.rglob('*') if f.is_file() and f.name!='manifest.json'}
        if actual!=expected:raise ValueError('Changed retained live transport evidence')
    else:
        if not a.root or not a.baseline:p.error('--root and --baseline are required')
        retain(a.root,a.baseline,a.out)
