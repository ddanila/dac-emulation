#!/usr/bin/env python3
"""Locate capacitor assembly sensitivity in logged trial order, not sorted time."""
import argparse
from fractions import Fraction as F
import json
from pathlib import Path

from analog_driver_replay import sha
from capacitor_stamp_review import parse as capacitor_parse, corrections
from linear_system_review import parse
from linear_precision_review import solve
from state_trajectory_review import fields, trials, samples, review as trajectory_review


def final_systems(log, systems):
    """Pair each solver return with its final solve; preserve retried timestamps."""
    by_id = {s['id']: s for s in systems}
    result, latest, current = [], None, None
    current_result = None
    for line in log.splitlines():
        if line.startswith('LINEAR_AUDIT end '):
            latest = int(fields(line, 2)['id'])
        elif line.startswith('TRUNC_AUDIT solver '):
            f = fields(line, 2)
            if latest is None or latest not in by_id:
                raise ValueError('Trial lacks a completed linear solve')
            current = by_id[latest]
            if any(current['metadata'][k] != f[k] for k in ('time', 'delta', 'order')):
                raise ValueError('Trial and final solve differ')
            current_result = int(f['result'])
            result.append(current)
            latest = None
        elif line.startswith('NODE_AUDIT '):
            f = fields(line, 1)
            if (current is None or any(f[k] != current['metadata'][k] for k in ('time', 'delta'))
                    or int(f['result']) != current_result):
                raise ValueError('Node lacks matching trial')
            matches = [i for i, name in current['names'].items() if name == f['name']]
            if len(matches) != 1:
                raise ValueError('Ambiguous node identity')
            index = matches[0]
            value = current['x'].get(index, F(0) if index == 0 else None)
            if value != F(float.fromhex(f['rhs'])):
                raise ValueError('Logged trial RHS differs from final solve')
    if latest is not None or not result:
        raise ValueError('Unfinished or absent trial linkage')
    return result


def compare(system, group):
    da, db, _ = corrections(group)
    a, b = dict(system['a']), dict(system['b'])
    for key, value in da.items(): a[key] = a.get(key, F(0)) + value
    for key, value in db.items(): b[key] = b.get(key, F(0)) + value
    corrected = dict(system, a=a, b=b)
    original, changed = solve(system, 160), solve(corrected, 160)
    original80, changed80 = solve(system, 80), solve(corrected, 80)
    indices = {name: i for i, name in system['names'].items()}
    data, ground = indices['n_cable_daten'], indices['host_receiver_gnd']
    voltage = lambda x: x[data] - x[ground]
    scaled = lambda x,y: float(max(abs(x[i]-v)/max(F(1), abs(v)) for i,v in y.items()))
    return {'systemId': system['id'], 'originalFrozenCableDataV': float(voltage(original)),
            'correctedFrozenCableDataV': float(voltage(changed)),
            'frozenCableDataChangeV': float(voltage(changed)-voltage(original)),
            'maximumSolutionChange': float(max(abs(changed[i]-v) for i,v in original.items())),
            'original80Vs160Scaled': scaled(original80, original),
            'corrected80Vs160Scaled': scaled(changed80, changed)}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('run', type=Path)
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args()
    parent = json.loads((args.run/'report.json').read_text())
    control = json.loads((args.run/'audit-control.json').read_text())
    if (not control['reproducedEvidence'] or control.get('auditWindow') != 'transition'
            or control['reportSha256'] != sha(args.run/'report.json')):
        raise ValueError('Requires matched transition-window logging control')
    for name, digest in parent['artifacts'].items():
        if sha(args.run/name) != digest: raise ValueError('Changed producer artifact: '+name)
    log = (args.run/'ngspice.log').read_text()
    systems, incomplete = parse(log)
    if incomplete: raise ValueError('Incomplete linear systems')
    linked = final_systems(log, systems)
    caps = capacitor_parse(log)
    audit, waveform = trials(log), samples((args.run/'host-trace.txt').read_text())
    selected = trajectory_review(audit, waveform, .001098011, .001098014, 10.)
    lookup = {s['id']: t for s,t in zip(linked, audit)}
    if len(linked) != len(audit): raise ValueError('Trial linkage count differs')
    rows = []
    for s in linked:
        if not .001098011 <= lookup[s['id']]['timeSeconds'] <= .001098014: continue
        t = selected['trials'][len(rows)]
        if (t['timeSeconds'] != float.fromhex(s['metadata']['time']) or
                t['deltaSeconds'] != float.fromhex(s['metadata']['delta'])):
            raise ValueError('Trajectory order differs')
        row = dict(t, **compare(s, caps[s['id']]))
        if max(row['original80Vs160Scaled'], row['corrected80Vs160Scaled']) > 1e-40:
            raise ValueError('Independent precision comparison failed')
        rows.append(row)
    first = lambda pred: next((r for r in rows if pred(r)), None)
    result = {'qualified': False, 'completed': True, 'scope': __doc__,
              'sourceReportSha256': sha(args.run/'report.json'),
              'auditControlSha256': sha(args.run/'audit-control.json'),
              'sources': {name: sha(Path(__file__).parent/name) for name in
                  ('capacitor_onset_review.py', 'capacitor_stamp_review.py', 'linear_system_review.py',
                   'linear_precision_review.py', 'state_trajectory_review.py', 'analog_driver_replay.py')},
              'diagnosticChangeLocatorV': 0.1, 'diagnosticExcursionLocatorV': 10.,
              'firstMaterialFrozenChange': first(lambda r: abs(r['frozenCableDataChangeV']) > .1),
              'firstExcursionTrial': first(lambda r: abs(r['cableDataV']) > 10),
              'firstSavedExcursion': first(lambda r: r['savedSample'] and abs(r['cableDataV']) > 10),
              'trials': rows,
              'boundary': 'Trial-order frozen-equation sensitivity, with original rhs and oldrhs kept distinct. Saved states are matched to oldrhs by exact timestamps and voltages. A corrected frozen solve does not rerun Newton, repair prior history, establish causality or demonstrate transient convergence. Locators are diagnostic, not physical acceptance budgets. Evidence is limited to the declared transition window.'}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2)+'\n')
    print(args.out)


if __name__ == '__main__': main()
