#!/usr/bin/env python3
"""Replay frozen live-transition equations and LTE histories, without qualification."""
import argparse
import hashlib
import json
import lzma
import re
from pathlib import Path
from linear_system_review import parse, review
from linear_precision_review import solve
from truncation_arithmetic_review import review_record
from analog_driver_replay import recorded_trtol


def assess(log):
    systems, incomplete = parse(log)
    records = [dict(re.findall(r'(\w+)=([^\s]+)', line)) for line in log.splitlines()
               if line.startswith('TRUNC_AUDIT error ')]
    if not records or 'STATE_AUDIT accepted ' not in log:
        raise ValueError('Missing accepted-state or LTE capture')
    accepted = []
    current = None
    for line in log.splitlines():
        if line.startswith(('STATE_AUDIT accepted ', 'STATE_AUDIT trial ')):
            if current is not None:
                if len(current['values']) != 4*int(current['metadata']['states']):
                    raise ValueError('Incomplete accepted-state capture')
                accepted.append(current)
            current = ({'metadata':dict(re.findall(r'(\w+)=([^\s]+)',line)), 'values':{}}
                       if line.startswith('STATE_AUDIT accepted ') else None)
        elif current is not None and line.startswith('STATE_AUDIT value '):
            fields=dict(re.findall(r'(\w+)=([^\s]+)',line))
            key=fields['history']+':'+fields['state']
            if key in current['values']:
                raise ValueError('Duplicate accepted-state entry')
            current['values'][key]=fields['value']
    lte = [review_record(r, 1e-15, recorded_trtol(log)) for r in records]
    # First rejection and terminal collapse, each at the final Newton iteration.
    steps = [dict(re.findall(r'(\w+)=([^\s]+)', line)) for line in log.splitlines() if line.startswith('TRUNC_AUDIT step ')]
    rejected = [s for s in steps if float.fromhex(s['proposed']) < .9*float.fromhex(s['delta'])]
    if not rejected:
        raise ValueError('No rejected timestep')
    selected = []
    for target in (float.fromhex(rejected[0]['time']), float.fromhex(rejected[-1]['time'])):
        candidates = [s for s in systems if float.fromhex(s['metadata']['time']) == target]
        if not candidates:
            raise ValueError('No matrix for truncation event')
        selected.append(candidates[-1])
    results = []
    for system in selected:
        solutions = [solve(system, precision) for precision in (80, 160)]
        change = {i: abs(solutions[-1][i]-system['x'][i]) for i in system['x']}
        worst = max(change, key=change.get)
        results.append({'id':system['id'], 'metadata':system['metadata'],
                        'largestSolutionChange':float(change[worst]),
                        'largestChangeNode':system['names'][worst],
                        'precisionAgreement':float(max(abs(solutions[0][i]-solutions[1][i]) for i in change)),
                        'originalBackwardError':review(system)['normwiseBackwardError'],
                        'highPrecisionBackwardError':review(dict(system,x=solutions[-1]))['normwiseBackwardError'],
                        'inductorCurrents':{system['names'][i]:{'recorded':float(system['x'][i]),'replayed':float(solutions[-1][i])}
                                            for i in change if system['names'][i].startswith('l') and '#branch' in system['names'][i]}})
    return {'qualified':False, 'acceptedStateTimes':[float.fromhex(s['metadata']['time']) for s in accepted], 'incompleteSystemIdsExcluded':incomplete, 'linearSystems':results,'lte':lte,
            'maximumLteProposalRelativeError':max(r['proposalRelativeRoundingError'] for r in lte),
            'boundary':'Frozen binary64 equations and histories only; does not recover assembly rounding, rerun nonlinear integration, or qualify a live trajectory.'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('log',type=Path);parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args();data=args.log.read_bytes()
    log=(lzma.decompress(data) if args.log.suffix=='.xz' else data).decode()
    result=assess(log);result['logSha256']=hashlib.sha256(data).hexdigest()
    result['sources']={name:hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest() for name in
                       ('live_state_review.py','linear_system_review.py','linear_precision_review.py','truncation_arithmetic_review.py','analog_driver_replay.py')}
    args.out.write_text(json.dumps(result,indent=2)+'\n')

if __name__=='__main__':main()
