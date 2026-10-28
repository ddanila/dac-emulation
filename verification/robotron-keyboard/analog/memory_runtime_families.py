#!/usr/bin/env python3
"""Bind unsupported storage-family controls to the selected continuous memory runtime."""
import argparse,json
from pathlib import Path
from array_family_probe import review as family_review
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent
WITNESS=HERE/'reports/parameter-late-refusal-controls/native-layout/build.json'


def review(root):
    build=json.loads((root/'build.json').read_text())
    if build!=json.loads(WITNESS.read_text()):raise ValueError('Different memory layout/runtime candidate')
    receipt=json.loads((root/'run.json').read_text())
    for family in ('alias','net','real','string'):
        for mode in ('disabled','dense','compact'):
            run=receipt['runs'][family+'-'+mode]
            if receipt['dependencies'].get(run['library'])!=build['outputs']['vvp/libvvp.so']:raise ValueError('Unbound family runtime')
    result=family_review(root)
    result['memoryRuntimeBuildSha256']=sha(root/'build.json')
    result['sameRuntimeNativeLayoutBuildSha256']=sha(WITNESS)
    result['scope']+=' Repeated on the exact runtime selected for continuous memory observation, including parameter, storage and read-port class guards. This tests whole-array dense/compact refusal; it does not claim complete memory lifecycle, native subclass allocation or continuous-board acceptance.'
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True);p.add_argument('--check',action='store_true');a=p.parse_args();r=review(a.root);out=a.root/'assessment.json'
    if a.check:
        if r!=json.loads(out.read_text()):raise ValueError('Changed family assessment')
    else:out.write_text(json.dumps(r,indent=2)+'\n')
