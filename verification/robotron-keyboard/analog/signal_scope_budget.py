#!/usr/bin/env python3
"""Compare complete reference/optimized images and initial board scan timings."""
import argparse,json,math
from pathlib import Path
import callback_signal_board_budget as previous
HERE=Path(__file__).resolve().parent


def review(root):
    board=previous.review(root)
    for kind in ('handles','links'):
        original=(root/(kind+'-before.txt')).read_bytes()
        for label in ('reference-before','reference-after'):
            if (root/(kind+'-'+label+'.txt')).read_bytes()!=original:raise ValueError('Reference/optimized '+kind+' images differ')
    scans={}
    for line in (root/'scope-scan-budget.txt').read_text().splitlines():
        a=line.split()
        if len(a)!=6 or a[0]!='SCOPE_SCAN' or a[2]!='64' or a[1] in scans:raise ValueError('Invalid scope scan budget')
        total,minimum,maximum=map(float,a[3:])
        if not all(math.isfinite(x) for x in (total,minimum,maximum)) or not 0<minimum<=total/64<=maximum:raise ValueError('Invalid scan timings')
        scans[a[1]]=dict(iterations=64,meanSeconds=total/64,minSeconds=minimum,maxSeconds=maximum)
    if set(scans)!={'handles-fast','handles-reference','links-reference'}:raise ValueError('Incomplete scan comparison')
    scans['links-fast']=board['linkScanTimings']
    ratios={kind:scans[kind+'-reference']['meanSeconds']/scans[kind+'-fast']['meanSeconds'] for kind in ('handles','links')}
    calls=board['initialStateProjection']['normalSnapshotCalls']
    return dict(qualified=False,controlsPassed=True,boardBindings=board,referenceImagesExactlyEqual=True,scanTimings=scans,measuredSpeedup=ratios,
                initialStateProjection=dict(normalSnapshotCalls=calls,referenceHandleAndLinkScanSeconds=calls*(scans['handles-reference']['meanSeconds']+scans['links-reference']['meanSeconds']),optimizedHandleAndLinkScanSeconds=calls*(scans['handles-fast']['meanSeconds']+scans['links-fast']['meanSeconds']),excludesOtherObserversStateGrowthAndReview=True),
                scope='Same initialized actual keyboard bridge and native inventories, with complete static scope validation performed once per optimized signal snapshot. Reference and optimized images agree byte-for-byte before and after all scans. Timings are local initial-state measurements, not guarantees for changing-state or combined transient execution.')


def run(source,bridge,icarus,out):
    previous.run(source,bridge,icarus,out)
    (out/'assessment.json').write_text(json.dumps(review(out),indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('source','bridge','icarus','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();run(a.source,a.bridge,a.icarus,a.out)
