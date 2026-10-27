#!/usr/bin/env python3
"""Run initialized board memory bindings on the exact guarded native runtime."""
import argparse,json,shutil
from pathlib import Path
import parameter_board_budget as capture
import memory_board_budget as board
from array_port_class import review as class_review
from memory_fault_continue import review as memory_review
from array_family_probe import review as family_review
from retained_evidence import check


def review(root):
    prior=board.review(root);guards=root/'guard-controls';check(guards)
    runtime=json.loads((root/'icarus-build.json').read_text())['outputs']
    for folder,fn in ((guards,class_review),(guards/'memory-regression',memory_review),(guards/'family-regression',family_review)):
        built=json.loads((folder/'build.json').read_text())['outputs']
        for name in runtime:
            if runtime[name]!=built[name]:raise ValueError('Guard controls use a different native runtime')
        if fn(folder)!=json.loads((folder/'assessment.json').read_text()):raise ValueError('Changed native guard assessment')
    return dict(qualified=False,controlsPassed=True,initializedMemoryControls=prior,matchingNativeGuardControls=True,
        scope='Complete initialized board memory/array bindings and unchanged scans run on the exact runtime outputs used by native exact read-port class, memory fault continuation and unsupported-family controls. All three memories, 56 parameters and preceding initial state bindings remain checked. This is tick-zero regression integration; no operational transient fault, ordinary lifecycle or full rollback qualification.')


def run(source,bridge,icarus,witness,out):
    check(witness)
    capture.run(source,bridge,icarus,out)
    shutil.copytree(witness,out/'native-layout')
    shutil.copytree(Path(__file__).resolve().parent/'reports/array-port-class',out/'guard-controls')
    (out/'assessment.json').write_text(json.dumps(review(out),indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('source','bridge','icarus','witness','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();run(a.source,a.bridge,a.icarus,a.witness,a.out)
