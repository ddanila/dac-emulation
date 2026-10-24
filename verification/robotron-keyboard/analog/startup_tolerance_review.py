#!/usr/bin/env python3
"""Retain matched startup tolerance controls without claiming full convergence."""
import argparse
import json
import lzma
import shutil
from pathlib import Path
from compare_firmware_io import sha
from host_waveform_comparison import rows, compare_samples
from live_transition_review import diagnostic
from numerical_voltage_budget import voltage_gate
from reset_release_driver_review import trace_summary, TRACES
from startup_grid_review import prefix, STEPS, WINDOW
from tolerance_controls_review import normalized
from trace_io import open_binary

HERE = Path(__file__).resolve().parent
BASELINE = HERE / 'reports/startup-grid-density'


def validate_pair(base, candidate, base_deck, candidate_deck):
    for run, scale in ((base, .1), (candidate, .01)):
        if (run['toleranceScale'] != scale or run['toleranceComponents'] != ['reltol']
                or run['haltNs'] != 2000 or run['stopNs'] != 1006000
                or not run['dacAnchored'] or run['exitCode'] != 0
                or run['timedOut'] or run['solverDiagnostic']):
            raise ValueError('Unexpected or failed startup control')
    ignored = {'elapsedSeconds', 'deckSha256', 'toleranceScale'}
    if ({k: v for k, v in base.items() if k not in ignored}
            != {k: v for k, v in candidate.items() if k not in ignored}):
        raise ValueError('Changed runtime, grid, stimulus or numerical settings')
    if normalized(base_deck, {'reltol': 1e-7}) != normalized(candidate_deck, {'reltol': 1e-8}):
        raise ValueError('Deck changed beyond relative tolerance')


def retain(root, out):
    out.mkdir(parents=True, exist_ok=False)
    for name, digest in json.loads((BASELINE / 'manifest.json').read_text()).items():
        if sha(BASELINE / name) != digest:
            raise ValueError('Changed baseline evidence')
    runs = {}
    cases = {}
    for step in STEPS:
        src = root / ('dense-tight-startup2us-' + step)
        base = BASELINE / 'dense' / step
        run = json.loads((src / 'run.json').read_text())
        validate_pair(json.loads((base / 'run.json').read_text()), run,
                      (base / 'io.cir').read_text(), (src / 'io.cir').read_text())
        if run['stepNs'] != float(step):
            raise ValueError('Incorrect refinement level')
        for name, digest in {**run['inputs'], 'io.cir': run['deckSha256'],
                             'sampling-grid.json': run['samplingGridSha256']}.items():
            if sha(src / name) != digest:
                raise ValueError('Changed input: ' + name)
        log = (src / 'ngspice.log').read_text()
        if 'condition met: stop' not in log or diagnostic(log):
            raise ValueError('Unclean diagnostic halt')
        traces = {name: trace_summary(src / name) for name in TRACES}
        if not all(t['firstSeconds'] == 0 and t['strictlyIncreasing']
                   and 2e-6 <= t['lastSeconds'] <= 2e-6 + float(step)*1e-9
                   for t in traces.values()):
            raise ValueError('Incomplete diagnostic waveform')
        dst = out / step
        dst.mkdir()
        for name in ('run.json', 'io.cir', 'sampling-grid.json'):
            shutil.copyfile(src / name, dst / name)
        for name in ('network_witness.txt', 'ngspice.log'):
            with open_binary(src / name) as source, lzma.open(dst / (name + '.xz'), 'wb') as target:
                shutil.copyfileobj(source, target)
        (dst / 'trace-endpoints.json').write_text(json.dumps(traces, indent=2) + '\n')
        runs[step] = run
        cases[step] = {'completedDiagnosticPrefix': True,
                       'networkSha256': traces['network_witness.txt']['sha256']}
    pairs = []
    sensitivity = {}
    for a, b in zip(STEPS, STEPS[1:]):
        signals = runs[a]['observationSignals']
        comparison = compare_samples(*(prefix(rows(out / s / 'network_witness.txt', signals, float(s)), WINDOW)
                                       for s in (a, b)))
        pairs.append({'coarse': a, 'fine': b, 'endSeconds': comparison['endSeconds'],
                      'signals': {n: {'unit': 'V' if n.lower().startswith('v(') else 'A',
                                      'maximumAbsoluteDifference': v['maximumDifferenceV'],
                                      'timeSeconds': v['timeSeconds']}
                                  for n, v in zip(signals, comparison['signals'])}})
    for step in STEPS:
        signals = runs[step]['observationSignals']
        comparison = compare_samples(*(prefix(rows(p / 'network_witness.txt', signals, float(step)), WINDOW)
                                       for p in (BASELINE / 'dense' / step, out / step)))
        sensitivity[step] = {'endSeconds': comparison['endSeconds'],
                             'signals': dict(zip(signals, comparison['signals']))}
    result = {'schema': 1, 'windowSeconds': [0, WINDOW], 'cases': cases,
              'refinementPairs': pairs, 'diagnosticVoltageGate': voltage_gate(pairs),
              'sameGridToleranceSensitivity': sensitivity,
              'baselineAssessmentSha256': sha(BASELINE / 'assessment.json'),
              'qualified': False,
              'scope': 'Tenfold relative-tolerance tightening on the same three startup grids and runtime. Comparison covers 0–1.9 us before the 2 us diagnostic halt, with the unchanged 1.006 ms declared horizon. No alignment or acceptance-limit change. This diagnostic cannot qualify reset release, repeat, physical models or production adoption.',
              'sources': {n: sha(HERE / n) for n in ('startup_tolerance_review.py', 'startup_grid_review.py',
                          'tolerance_controls_review.py', 'host_waveform_comparison.py',
                          'numerical_voltage_budget.py', 'trace_io.py')}}
    (out / 'assessment.json').write_text(json.dumps(result, indent=2) + '\n')
    (out / 'manifest.json').write_text(json.dumps({str(p.relative_to(out)): sha(p)
        for p in sorted(out.rglob('*')) if p.is_file()}, indent=2) + '\n')
    print(json.dumps(result['diagnosticVoltageGate'], indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runs', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    retain(args.runs, args.out)
