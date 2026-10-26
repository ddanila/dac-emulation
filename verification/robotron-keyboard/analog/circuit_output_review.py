#!/usr/bin/env python3
"""Review circuit-wide pending-output coverage without claiming private HDL rollback."""
import argparse
import json
import math
from pathlib import Path
import re
from audit_log import records
from delayed_corruption_review import assess as base_assess, fault
from event_state_review import check
from filter_truncation_log import diagnostic
from staged_output_review import STATE_RECORDS


def runtime_summary(path):
    # Circuit records receive a complete structural review in inventory(). Only
    # their exact record prefixes bypass generic solver-message classification.
    state_records = STATE_RECORDS + ('C_SUM ', 'C_PORT ', 'C_EVENT ')
    count = None; failure = None; sorry = False
    for line in records(path):
        if line.startswith(state_records): continue
        if line.startswith(('C_CORRUPT ', 'E_CORRUPT ')):
            raise ValueError('Unexpected corruption in positive control')
        failure = failure or diagnostic(line)
        sorry = sorry or 'SORRY:' in line
        matches = re.findall(r'No\. of Data Rows\s*:\s*(\d+)', line)
        if matches:
            if count is not None or len(matches) != 1: raise ValueError('Multiple completion counts')
            count = int(matches[0])
    return {'count': count, 'diagnostic': failure, 'sorry': sorry}


def inventory(path):
    active = False; size = None; ports = None; layout = None; current = None
    snapshots = 0; events = 0; external_events = 0; instances = set(); ordinals = 0
    for line in records(path, ('H_BEGIN ', 'H_END', 'C_')):
        a = line.split()
        if a[0] == 'H_BEGIN':
            if active: raise ValueError('Nested circuit snapshot')
            active = True; size = None; ports = []; current = None
        elif a[0] == 'C_SUM':
            if not active or size is not None or len(a) != 2 or int(a[1]) <= 0:
                raise ValueError('Invalid circuit output count')
            size = int(a[1])
        elif a[0] == 'C_PORT':
            if not active or size is None or len(a) != 10:
                raise ValueError('Invalid circuit output inventory')
            index, instance, node, own = map(int, a[1:5]); flags = tuple(map(int, a[7:10]))
            if index != len(ports) or index >= size or min(instance, node) < 0 or own not in (0, 1) or any(v not in (0, 1) for v in flags):
                raise ValueError('Invalid circuit output identity or flags')
            current = (index, instance, node, own, a[5], a[6]); ports.append(current); ordinals = 0
            if not own: instances.add(a[5])
        elif a[0] == 'C_EVENT':
            if not active or current is None or len(a) != 9:
                raise ValueError('Orphan circuit output event')
            index, ordinal = map(int, a[1:3]); when, posted = map(float.fromhex, a[3:5])
            removed = int(a[5]); removed_at = float.fromhex(a[6]); int(a[7]); int(a[8])
            if index != current[0] or ordinal != ordinals or not all(map(math.isfinite, (when, posted, removed_at))) or removed not in (0, 1) or when < posted or (not removed and removed_at != 0):
                raise ValueError('Invalid circuit event sequence')
            ordinals += 1; events += 1; external_events += int(not current[3])
        elif a[0] == 'H_END':
            if not active or size is None or len(ports) != size:
                raise ValueError('Incomplete circuit output inventory')
            if layout is not None and layout != ports:
                raise ValueError('Changed circuit output identities')
            layout = ports; snapshots += 1; active = False
        elif a[0] != 'C_CORRUPT':
            raise ValueError('Unknown circuit record')
    if active or not snapshots or not instances or not any(p[3] for p in layout):
        raise ValueError('Missing circuit-wide output coverage')
    return {'snapshots': snapshots, 'outputs': len(layout), 'controllerOutputs': sum(p[3] for p in layout),
            'otherInstances': sorted(instances), 'pendingEventObservations': events,
            'otherModelPendingEventObservations': external_events,
            'inventory': [{'index': p[0], 'instanceIndex': p[1], 'nodeIndex': p[2], 'controllerOwned': bool(p[3]),
                           'instance': p[4], 'node': p[5]} for p in layout]}


def external_fault(path, after):
    lines = list(records(path, ('C_CORRUPT ',)))
    if len(lines) != 1: raise ValueError('Missing unique external mutation')
    match = re.fullmatch(r'C_CORRUPT pending index=(\d+) instance=(\S+)', lines[0])
    if not match: raise ValueError('Malformed external mutation')
    data = inventory(path)
    selected = [p for p in data['inventory'] if p['index'] == int(match[1])]
    if len(selected) != 1 or selected[0]['controllerOwned'] or selected[0]['instance'] != match[2]:
        raise ValueError('Mutation was not in an independently observed external output')
    return dict(fault(path, after, mutation_line=lines[0]), mutatedOutput=selected[0], mutation='output pending flag')


def assess(root, baseline):
    result = base_assess(root, baseline, fault_review=external_fault, summary_review=runtime_summary)
    result['circuitOutputs'] = inventory(root / 'check/ngspice.log')
    if not result['circuitOutputs']['otherModelPendingEventObservations']:
        raise ValueError('No pending events witnessed outside controller')
    result['scope'] = 'Complete 20-us combined-fix observer control covering all digital output queues from current pointers and output pending/modified/changed flags; immediate/delayed faults target another model.'
    result['notEstablished'] = ['Long post-reset state qualification', 'Instance queues, past/free output history, private HDL events',
                                'Full startup/repeat/supply recovery', 'Numerical convergence', 'Device admission']
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, required=True); p.add_argument('--baseline', type=Path)
    p.add_argument('--out', type=Path); p.add_argument('--check-manifest', action='store_true')
    a = p.parse_args()
    if a.check_manifest: check(a.root)
    else:
        if not a.baseline or not a.out: p.error('Need baseline and output')
        result = assess(a.root, a.baseline)
        with a.out.open('x') as f: json.dump(result, f, indent=2); f.write('\n')
