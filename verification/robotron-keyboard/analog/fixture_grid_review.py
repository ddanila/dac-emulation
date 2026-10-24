#!/usr/bin/env python3
"""Retain matched fixture-scheduling controls and absolute-time refinement."""
import argparse
import json
import lzma
import shutil
from pathlib import Path
from reset_release_driver_review import trace_summary, completed, TRACES
from live_transition_review import diagnostic
from host_waveform_comparison import rows, compare_samples
from numerical_voltage_budget import voltage_gate
from network_refinement_review import events
from ttl7406_probe import sha

HERE = Path(__file__).resolve().parent
CASES = ('control', '25', '12.5', '6.25')


def retain(root, out):
    out.mkdir(parents=True, exist_ok=False)
    receipts, cases = {}, {}
    for name in CASES:
        src = root / ('fixture-grid-reset-' + name)
        dst = out / name
        dst.mkdir()
        run = json.loads((src / 'run.json').read_text())
        receipts[name] = run
        if not run.get('externalDependencies') or sha(src / 'io.cir') != run['deckSha256']:
            raise ValueError('Missing dependencies or changed deck')
        for file, digest in run['inputs'].items():
            if sha(src / file) != digest:
                raise ValueError('Changed input')
        for file in ('io.cir', 'run.json'):
            shutil.copyfile(src / file, dst / file)
        log = (src / 'ngspice.log').read_text()
        with lzma.open(dst / 'ngspice.log.xz', 'wt') as stream:
            stream.write(log)
        traces = {file: trace_summary(src / file) for file in TRACES if (src / file).exists()}
        (dst / 'trace-endpoints.json').write_text(json.dumps(traces, indent=2) + '\n')
        cases[name] = {'completed': completed(run, traces, diagnostic(log)),
                       'diagnostic': diagnostic(log), 'timedOut': run['timedOut'],
                       'bus': events(log)}
    # Every experimental option is identical except grid enablement and max step.
    ignored = {'elapsedSeconds', 'exitCode', 'timedOut', 'solverDiagnostic', 'deckSha256',
               'stepNs', 'fixtureCrossingGuardPs'}
    identity = lambda run: {k: v for k, v in run.items() if k not in ignored}
    for name, run in receipts.items():
        if identity(run) != identity(receipts['control']):
            raise ValueError('Unmatched runtime, circuit or experimental controls')
        if run['fixtureCrossingGuardPs'] != (None if name == 'control' else .25):
            raise ValueError('Unexpected scheduling guard')
        if run['stepNs'] != (25 if name == 'control' else float(name)):
            raise ValueError('Unexpected refinement step')
    pairs = []
    for a, b in (('control', '25'), ('25', '12.5'), ('12.5', '6.25')):
        if not (cases[a]['completed'] and cases[b]['completed']):
            continue
        signals = receipts[a]['observationSignals']
        result = compare_samples(*(rows(root / ('fixture-grid-reset-' + name) / 'network_witness.txt',
                                       signals, receipts[name]['stepNs']) for name in (a, b)))
        ea, eb = cases[a]['bus'], cases[b]['bus']
        pairs.append({'coarse': a, 'fine': b, 'endSeconds': result['endSeconds'],
            'signals': {signal: {'unit': 'V' if signal.lower().startswith('v(') else 'A',
                'maximumAbsoluteDifference': value['maximumDifferenceV'], 'timeSeconds': value['timeSeconds']}
                for signal, value in zip(signals, result['signals'])},
            'busEventsIdentical': ea == eb, 'busSamplesIdentical': ea['samples'] == eb['samples'],
            'busEdgeTimingDifferencePs': [y-x for x,y in zip(ea['edgeTimesPs'],eb['edgeTimesPs'])]
                if len(ea['edgeTimesPs']) == len(eb['edgeTimesPs']) else None,
            'latchesMatch': ea['latchesMatch'] and eb['latchesMatch']})
    control = next((pair for pair in pairs if pair['coarse'] == 'control'), None)
    pairs = [pair for pair in pairs if pair['coarse'] != 'control']
    result = {'schema': 1, 'cases': cases, 'controlComparison': control, 'refinementPairs': pairs,
        'voltageGate': voltage_gate(pairs) if len(pairs) == 2 else None,
        'numericallyQualified': False, 'electricallyQualified': False,
        'productionDefaultChangeAuthorized': False,
        'scope': 'Bounded live prefix with ideal external clock/reset. Matched precision window and fixed crossing guard; no circuit or tolerance changes. Trace tails and hashes retain provenance; full raw waveforms remain in local run directories. This cannot qualify full-repeat traffic or physical device models.',
        'sources': {name: sha(HERE / name) for name in ('fixture_grid_review.py', 'fixture_crossing_grid.py',
            'live_transition_probe.py', 'reset_release_driver_review.py', 'live_transition_review.py',
            'host_waveform_comparison.py', 'network_refinement_review.py', 'numerical_voltage_budget.py')}}
    (out / 'assessment.json').write_text(json.dumps(result, indent=2) + '\n')
    manifest = {str(p.relative_to(out)): sha(p) for p in sorted(out.rglob('*')) if p.is_file()}
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runs', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    if args.check:
        for name, digest in json.loads((args.out / 'manifest.json').read_text()).items():
            if sha(args.out / name) != digest:
                raise ValueError('Changed retained evidence: ' + name)
        print('Fixture-grid evidence hashes verified')
    else:
        if args.runs is None:
            parser.error('--runs is required')
        result = retain(args.runs, args.out)
        print(json.dumps(result['cases'], indent=2))
