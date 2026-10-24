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
from common_samples import samples_at, compare_native

HERE = Path(__file__).resolve().parent
CASES = ('control', '25', '12.5', '6.25')


def validate_receipts(receipts, experiment):
    # Only the declared experimental variable and maximum timestep may differ.
    ignored = {'elapsedSeconds', 'exitCode', 'timedOut', 'solverDiagnostic', 'deckSha256',
               'stepNs', 'fixtureCrossingGuardPs', 'method', 'samplingGridSha256'}
    identity = lambda run: {k: v for k, v in run.items() if k not in ignored}
    if experiment not in ('crossings','integration','sampling'):raise ValueError('Unknown experiment')
    expected_grid=receipts['25'].get('samplingGridSha256') if experiment=='sampling' else None
    if experiment=='sampling' and not expected_grid:raise ValueError('Missing sampling grid')
    for name, run in receipts.items():
        if run.get('samplingGridSha256') != (None if name=='control' else expected_grid):
            raise ValueError('Unmatched sampling grid')
        if identity(run) != identity(receipts['control']):
            raise ValueError('Unmatched runtime, circuit or experimental controls')
        expected_method = 'gear' if experiment == 'integration' and name != 'control' else 'trap'
        if run['method'] != expected_method:
            raise ValueError('Unexpected integration method')
        if run['fixtureCrossingGuardPs'] != (None if name == 'control' and experiment == 'crossings' else .25):
            raise ValueError('Unexpected scheduling guard')
        if run['stepNs'] != (25 if name == 'control' else float(name)):
            raise ValueError('Unexpected refinement step')


def retain(root, out, experiment="crossings"):
    def source(name):
        if experiment == "sampling":
            return root / ("fixture-grid-sampling-"+name)
        if experiment == "integration":
            return root / ("fixture-grid-reset-25" if name == "control" else "fixture-grid-gear-"+name)
        return root / ("fixture-grid-reset-"+name)
    out.mkdir(parents=True, exist_ok=False)
    receipts, cases = {}, {}
    for name in CASES:
        src = source(name)
        dst = out / name
        dst.mkdir()
        run = json.loads((src / 'run.json').read_text())
        receipts[name] = run
        if not run.get('externalDependencies') or sha(src / 'io.cir') != run['deckSha256']:
            raise ValueError('Missing dependencies or changed deck')
        for file, digest in run['inputs'].items():
            if sha(src / file) != digest:
                raise ValueError('Changed input')
        if run.get('samplingGridSha256'):
            if sha(src/'sampling-grid.json')!=run['samplingGridSha256']:raise ValueError('Changed sampling grid')
            shutil.copyfile(src/'sampling-grid.json',dst/'sampling-grid.json')
        for file in ('io.cir', 'run.json'):
            shutil.copyfile(src / file, dst / file)
        log = (src / 'ngspice.log').read_text()
        with lzma.open(dst / 'ngspice.log.xz', 'wt') as stream:
            stream.write(log)
        traces = {file: trace_summary(src / file) for file in TRACES if any(Path(str(src/file)+suffix).exists() for suffix in ('','.gz','.xz'))}
        (dst / 'trace-endpoints.json').write_text(json.dumps(traces, indent=2) + '\n')
        cases[name] = {'completed': completed(run, traces, diagnostic(log)),
                       'diagnostic': diagnostic(log), 'timedOut': run['timedOut'],
                       'bus': events(log)}
    validate_receipts(receipts, experiment)
    pairs = []
    for a, b in (('control', '25'), ('25', '12.5'), ('12.5', '6.25')):
        if not (cases[a]['completed'] and cases[b]['completed']):
            continue
        signals = receipts[a]['observationSignals']
        result = compare_samples(*(rows(source(name) / 'network_witness.txt',
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
    common=None
    if experiment=='sampling':
        times=json.loads((source('25')/'sampling-grid.json').read_text())['timesSeconds']
        signals=receipts['25']['observationSignals']
        common={'signals':signals,'samples':{name:samples_at(rows(source(name)/'network_witness.txt',signals,receipts[name]['stepNs']),times) for name in CASES if cases[name]['completed']},
            'scope':'Actual nearest saved samples with explicit time offsets; no interpolation. Added breakpoints can change solver trajectory. These selected times do not substitute for the full-window gate.'}
        common['comparisons']=[{'coarse':a,'fine':b,**compare_native(common['samples'][a],common['samples'][b],signals)}
            for a,b in (('25','12.5'),('12.5','6.25')) if a in common['samples'] and b in common['samples']]
    control = next((pair for pair in pairs if pair['coarse'] == 'control'), None)
    pairs = [pair for pair in pairs if pair['coarse'] != 'control']
    result = {'schema': 1, 'experiment': experiment, 'commonSamples': common, 'cases': cases, 'controlComparison': control, 'refinementPairs': pairs,
        'voltageGate': voltage_gate(pairs) if len(pairs) == 2 else None,
        'numericallyQualified': False, 'electricallyQualified': False,
        'productionDefaultChangeAuthorized': False,
        'scope': 'Bounded live prefix with ideal external clock/reset. Matched precision window and fixed crossing guard; no physical board-model or tolerance changes. Isolated grid sources change scheduling and solver matrix structure, so their control comparison does not isolate scheduling alone. Trace tails and hashes retain provenance; full raw waveforms remain in local run directories. This cannot qualify full-repeat traffic or physical device models.',
        'sources': {name: sha(HERE / name) for name in ('fixture_grid_review.py', 'fixture_crossing_grid.py',
            'live_transition_probe.py', 'reset_release_driver_review.py', 'live_transition_review.py',
            'host_waveform_comparison.py', 'network_refinement_review.py', 'numerical_voltage_budget.py', 'trace_io.py', 'sampling_grid.py', 'common_samples.py')}}
    (out / 'assessment.json').write_text(json.dumps(result, indent=2) + '\n')
    manifest = {str(p.relative_to(out)): sha(p) for p in sorted(out.rglob('*')) if p.is_file()}
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runs', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--experiment', choices=('crossings','integration','sampling'), default='crossings')
    args = parser.parse_args()
    if args.check:
        for name, digest in json.loads((args.out / 'manifest.json').read_text()).items():
            if sha(args.out / name) != digest:
                raise ValueError('Changed retained evidence: ' + name)
        print('Fixture-grid evidence hashes verified')
    else:
        if args.runs is None:
            parser.error('--runs is required')
        result = retain(args.runs, args.out, args.experiment)
        print(json.dumps(result['cases'], indent=2))
