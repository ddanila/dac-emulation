#!/usr/bin/env python3
"""Bounded-cache circuit inventory review; validates every snapshot and event."""
import argparse
import json
import math
from pathlib import Path
from audit_log import records


def inventory_fast(path):
    active = False; size = None; ports = None; layout = None; current = None
    snapshots = 0; events = 0; external_events = 0; instances = set(); ordinals = 0
    from functools import lru_cache
    @lru_cache(maxsize=1024)
    def port(line):
        a=line.split()
        if len(a)!=10:raise ValueError('Invalid circuit output inventory')
        index,instance,node,own=map(int,a[1:5]);flags=tuple(map(int,a[7:10]))
        if min(instance,node)<0 or own not in (0,1) or any(v not in (0,1) for v in flags):
            raise ValueError('Invalid circuit output identity or flags')
        return (index,instance,node,own,a[5],a[6])
    for line in records(path, ('H_BEGIN ', 'H_END', 'C_')):
        if line.startswith('C_PORT') and (len(line)==6 or line[6].isspace()):
            if not active or size is None:raise ValueError('Invalid circuit output inventory')
            current=port(line);index,instance,node,own,name,_=current
            if index!=len(ports) or index>=size:raise ValueError('Invalid circuit output identity or flags')
            ports.append(current);ordinals=0
            if not own:instances.add(name)
            continue
        a = line.split()
        if a[0] == 'H_BEGIN':
            if active: raise ValueError('Nested circuit snapshot')
            active = True; size = None; ports = []; current = None
        elif a[0] == 'C_SUM':
            if not active or size is not None or len(a) != 2 or int(a[1]) <= 0:
                raise ValueError('Invalid circuit output count')
            size = int(a[1])
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


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('log', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    result = inventory_fast(args.log)
    with args.out.open('x') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
