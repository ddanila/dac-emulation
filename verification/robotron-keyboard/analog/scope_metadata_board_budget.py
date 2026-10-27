#!/usr/bin/env python3
"""Review initialized keyboard scope identities, residual object families and cost."""
import argparse,json,math
from collections import Counter
from pathlib import Path
import signal_scope_budget as previous
from scope_metadata_bindings import parse,validate


def review(root):
    prior=previous.review(root)
    for stem in ('metadata','metadata-references'):
        if (root/(stem+'-before.txt')).read_bytes()!=(root/(stem+'-after.txt')).read_bytes():raise ValueError('Metadata scan changed initialized state')
    names=('metadata-before.txt','metadata-references-before.txt','handle-scopes.txt','handles-before.txt')
    state=parse([line for name in names for line in (root/name).read_text().splitlines()])
    bindings=validate(state)
    if state['metadata']['tick']!=0:raise ValueError('Diagnostic advanced HDL time')
    refs=state['reference'];scope_ptrs={s['pointer'] for s in refs['scopes']};signal_ptrs={s['pointer'] for s in state['signals']['rows']}
    categories={'scopes':Counter(),'admittedSignals':Counter(),'remainingObjects':Counter()}
    for obj in refs['objects']:
        key='scopes' if obj['pointer'] in scope_ptrs else 'admittedSignals' if obj['pointer'] in signal_ptrs else 'remainingObjects'
        categories[key][str(obj['type'])]+=1
    scans={}
    for line in (root/'metadata-budget.txt').read_text().splitlines():
        a=line.split()
        if len(a)!=6 or a[0]!='SCOPE_SCAN' or a[1] not in ('metadata','references') or a[1] in scans or a[2]!='64':raise ValueError('Invalid metadata budget')
        total,minimum,maximum=map(float,a[3:])
        if not all(math.isfinite(x) for x in (total,minimum,maximum)) or not 0<minimum<=total/64<=maximum:raise ValueError('Invalid metadata timing')
        scans[a[1]]=dict(iterations=64,meanSeconds=total/64,minSeconds=minimum,maxSeconds=maximum)
    if set(scans)!={'metadata','references'}:raise ValueError('Incomplete metadata budget')
    sizes={key:(root/name).stat().st_size for key,name in zip(('metadata','references'),names)}
    calls=prior['initialStateProjection']['normalSnapshotCalls']
    return dict(qualified=False,controlsPassed=True,priorSignalScopeControls=prior,bindings=bindings,
        registeredObjectFamilies={k:dict(sorted(v.items())) for k,v in categories.items()},
        scopeFamilies=dict(sorted(Counter(str(s['type']) for s in state['metadata']['scopes']).items())),
        imageBytes=sizes,scanTimings=scans,initialStateProjection=dict(normalSnapshotCalls=calls,
            logicalBytes=calls*sum(sizes.values()),scanSeconds=calls*sum(v['meanSeconds'] for v in scans.values()),
            excludesStateGrowthOtherObserversAndReview=True),
        scope='Actual initialized keyboard bridge metadata and scope/signal identity joins, repeated before first coroutine advance. Residual families enumerate unbound object identities, not payload coverage. Local initial-state timings and byte projections do not qualify operational state growth, complete board coverage or total capture/review cost.')


def run(source,bridge,icarus,out):
    previous.run(source,bridge,icarus,out)
    (out/'assessment.json').write_text(json.dumps(review(out),indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('source','bridge','icarus','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();run(a.source,a.bridge,a.icarus,a.out)
