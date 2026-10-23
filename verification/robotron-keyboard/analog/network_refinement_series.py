#!/usr/bin/env python3
"""Three-level absolute-time refinement; completion does not imply convergence."""
import argparse,json
from pathlib import Path
from network_refinement_review import review

def series(paths):
 if len(paths)!=3:raise ValueError('Exactly three refinement levels required')
 receipts=[json.loads((p/'run.json').read_text()) for p in paths]
 guards=[r['fixtureCrossingGuardPs'] for r in receipts]
 if any(g is None or g<=0 for g in guards) or guards[0]!=2*guards[1] or guards[1]!=2*guards[2]:raise ValueError('Fixture guard must halve at each level')
 pairs=[review(paths[:2]),review(paths[1:])]
 ratios={n:{metric: b[metric]/a[metric] if a[metric] else None for metric in ('maximumAbsoluteDifference','rmsDifference','meanAbsoluteDifference')} for n,a in pairs[0]['signals'].items() for b in [pairs[1]['signals'][n]]}
 return {'completed':True,'qualified':False,'pairs':pairs,'fineToCoarseDifferenceRatios':ratios,
 'boundary':'Absolute-time sample-grid comparisons with unchanged circuit and stimulus. Ratios are observations, not an accuracy budget. No alignment or exclusion of unknown/transition intervals. Physical device admission and representative traffic remain independent gates.'}
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('runs',nargs=3,type=Path);p.add_argument('--out',type=Path,required=True);a=p.parse_args();a.out.write_text(json.dumps(series(a.runs),indent=2)+'\n')
