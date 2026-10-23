#!/usr/bin/env python3
"""Compare isolated recovery hypotheses without treating sensitivity as accuracy."""
import argparse
import json
import lzma
from pathlib import Path

from gate_switching_probe import sha
from serial_path_probe import interpolate


def trace(path):
    with lzma.open(path,'rt') as stream:
        next(stream)
        return [list(map(float,line.split())) for line in stream]


def difference(root,a,b):
    ra,rb=(trace(root/n/'trace.txt.xz') for n in (a,b))
    # Both inputs cover the same original event with four microseconds prelude.
    low,high=3.5e-6,5e-6
    peak=0;when=None
    for source,target in ((ra,rb),(rb,ra)):
        for row in source:
            if low<=row[0]<=high:
                delta=abs(row[2]-interpolate(target,row[0],2))
                if delta>peak:peak,when=delta,row[0]
    return dict(first=a,second=b,maximumDifferenceV=peak,timeFromReplayStartSeconds=when,
                intervalSeconds=[low,high])


def review(root):
    report=json.loads((root/'report.json').read_text())
    if not report['completed']:raise ValueError('Incomplete recovery investigation')
    for name,digest in report['artifacts'].items():
        if sha(root/name)!=digest:raise ValueError('Changed recovery capture: '+name)
    names=('long-prelude','half-step','quarter-step','junction-2pf','junction-2pf-half')
    if not all(report['runs'][n]['completed'] for n in names):raise ValueError('Incomplete paired replay')
    return dict(completed=True,qualified=False,boardAdmission=False,sourceSha256=sha(Path(__file__)),
        recoveryReportSha256=sha(root/'report.json'),
        refinement=[difference(root,'long-prelude','half-step'),difference(root,'half-step','quarter-step')],
        alternativeRefinement=difference(root,'junction-2pf','junction-2pf-half'),
        sameStepDeviceSensitivity=difference(root,'long-prelude','junction-2pf'),
        failedControls={n:r['error'] for n,r in report['runs'].items() if not r['completed']},
        boundary='Absolute replay time, piecewise-linear comparison at the union of retained knots, no alignment or discarded transitions within the event interval. Two candidates pass selected device screens; their disagreement demonstrates non-uniqueness, not a physical error bound. A failed longer prelude prevents declaring arbitrary initialization independence.')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();a.out.write_text(json.dumps(review(a.root),indent=2)+'\n')
