#!/usr/bin/env python3
"""Replay recorded DAC voltages without HDL feedback; diagnostic stimulus only."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess

from failure_evidence import solver_diagnostic
from ngspice_runtime import identify, verify


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def reduce_linear(points, tolerance):
    """Retain knots with a bounded error against the sampled linear interpolant."""
    if not math.isfinite(tolerance) or tolerance <= 0 or len(points) < 2:
        raise ValueError('Expected samples and a positive finite interpolation budget')
    if any(not all(map(math.isfinite, p)) for p in points) or any(
            b[0] <= a[0] for a, b in zip(points, points[1:])):
        raise ValueError('Samples must be finite and strictly ordered')
    keep = {0, len(points)-1}
    pending = [(0, len(points)-1)]
    while pending:
        left, right = pending.pop()
        a, b = points[left], points[right]
        largest, index = tolerance, None
        for i in range(left+1, right):
            t, value = points[i]
            expected = a[1] + (t-a[0])/(b[0]-a[0])*(b[1]-a[1])
            error = abs(value-expected)
            if error > largest:
                largest, index = error, i
        if index is not None:
            keep.add(index)
            pending.extend(((left, index), (index, right)))
    return [points[i] for i in sorted(keep)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path, help='Verified all-driver boundary replay directory')
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--omit-capture-knot', action='store_true',
                        help='Diagnostic control: remove the capture-end PWL knot with at most 1 nV change')
    args = parser.parse_args()
    source, out = args.source.resolve(), args.out.resolve()
    parent = json.loads((source/'report.json').read_text())
    if not parent.get('allDrivers') or not parent.get('reproducedFailure'):
        raise ValueError('Expected a verified failed replay with all driver observations')
    for name in ('io.cir', 'boundary-trace.txt'):
        if sha(source/name) != parent['artifacts'][name]:
            raise ValueError('Source artifact differs: ' + name)
    original_path = Path(parent['sourceDirectory'])/'report.json'
    if sha(original_path) != parent['sourceReportSha256']:
        raise ValueError('Original fixture report differs')
    original = json.loads(original_path.read_text())
    assumptions = original['assumptions']
    if assumptions.get('electricalCpuPullups') or assumptions.get('electricalLogicPullups'):
        raise ValueError('Replay does not cover additional analog control drivers')
    runtime, env = identify(parent['ngspiceRuntime']['executable']['path'],
                            parent['ngspiceRuntime']['spinit']['path'])
    if runtime != parent['ngspiceRuntime']:
        raise ValueError('Runtime differs')
    lines = (source/'boundary-trace.txt').read_text().splitlines()
    header = lines[0].split()
    rows = [tuple(map(float, line.split())) for line in lines[1:]]
    if header != ['time', *parent['signals']] or any(len(row) != len(header) for row in rows):
        raise ValueError('Source trace layout differs')
    nodes = ['data_intent', 'clock_intent', 'led0_v', 'led1_v', *[f'sink{i}' for i in range(13)]]
    endpoint = rows[-1][0]
    stop = endpoint + 2e-9
    budget = 1e-12
    drives, sources = {}, []
    for node in nodes:
        column = header.index(f'v({node})')
        points = [(row[0], row[column]) for row in rows]
        reduced = reduce_linear(points, budget)
        recent = [p for p in points if p[0] >= endpoint-1e-9]
        if node == 'data_intent':
            # Explicit diagnostic continuation of the observed rising edge.
            # No firmware behavior beyond the failed recording is inferred.
            if not 0 < points[-1][1] < 2.5 or points[-1][1] <= recent[0][1]:
                raise ValueError('Expected the recorded rising data edge')
            continuation = [(endpoint + (5-points[-1][1])/5e9, 5.0), (stop, 5.0)]
        else:
            if any(abs(p[1]-points[-1][1]) > budget for p in recent):
                raise ValueError('Another driver is moving at the capture boundary: ' + node)
            continuation = [(stop, points[-1][1])]
        points_out = reduced + continuation
        omitted_error = None
        if args.omit_capture_knot:
            a, b = reduced[-2], continuation[0]
            expected = a[1]+(endpoint-a[0])/(b[0]-a[0])*(b[1]-a[1])
            omitted_error = abs(expected-reduced[-1][1])
            if omitted_error > 1e-9:
                raise ValueError('Capture-knot omission exceeds diagnostic budget: '+node)
            points_out = reduced[:-1]+continuation
        sources.append(f'Vreplay_{node} {node} 0 PWL(' + ' '.join(
            f'{t:.17g} {v:.17g}' for t,v in points_out) + ')')
        drives[node] = {'retainedKnots': len(reduced), 'continuation': continuation,
                        'omittedCaptureKnotErrorV': omitted_error}
    deck = (source/'io.cir').read_text()
    removed = []
    kept = []
    names = ('Amatrix ', 'Arxdata ', 'Arxclock ', 'Afixture ', 'Ahdl ', 'Adrive ', 'Acolumns ',
             '.model hdl ', '+ lib_args=')
    for line in deck.splitlines():
        if line.startswith(names):
            removed.append(line)
        else:
            kept.append(line)
    if len(removed) != len(names) or any(sum(line.startswith(name) for line in removed) != 1 for name in names):
        raise ValueError('Unexpected digital interface layout')
    deck = '\n'.join(kept)+'\n'
    if len(re.findall(r'^\.tran .+$', deck, re.M)) != 1:
        raise ValueError('Expected one deck transient analysis')
    deck = re.sub(r'^\.tran .+$', f'.tran {assumptions["stepNs"]}n {stop:.17g}', deck, flags=re.M)
    deck = deck.replace('\n.control\n', '\n'+'\n'.join(sources)+'\n.control\n')
    out.mkdir(parents=True, exist_ok=False)
    (out/'io.cir').write_text(deck)
    report = {'qualified': False, 'scope': __doc__, 'completed': False,
              'sourceReportSha256': sha(source/'report.json'), 'sourceDirectory': str(source),
              'ngspiceRuntime': runtime, 'deckSha256': sha(out/'io.cir'),
              'sources': {name: sha(Path(__file__).parent/name) for name in
                          ('analog_driver_replay.py', 'ngspice_runtime.py', 'failure_evidence.py')},
              'recordedEndpointSeconds': endpoint, 'stopSeconds': stop,
              'interpolationBudgetV': budget,
              'omitCaptureKnot': args.omit_capture_knot,
              'captureKnotOmissionBudgetV': 1e-9 if args.omit_capture_knot else None, 'drivers': drives, 'removedInterfaceLines': removed,
              'boundary': 'Recorded sampled DAC interpolation, followed by an explicit data-edge continuation to 5 V at 5 V/ns and held other drivers. Not an observed firmware continuation or full-board qualification.'}
    try:
        verify(runtime)
        with (out/'ngspice.log').open('w') as log:
            process = subprocess.run([runtime['executable']['path'], '-n', '-b', 'io.cir'],
                                     cwd=out, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=600)
        verify(runtime)
        report['exitCode'] = process.returncode
        report['solverDiagnostic'] = solver_diagnostic((out/'ngspice.log').read_text())
        with (out/'trace.txt').open() as stream:
            next(stream)
            previous, count = None, 0
            for line in stream:
                row = list(map(float, line.split()))
                if (len(row) != 3 or not all(map(math.isfinite, row))
                        or (previous is not None and row[0] < previous)):
                    raise ValueError('Malformed replay waveform')
                if previous is None and row[0] != 0:
                    raise ValueError('Replay waveform does not start at zero')
                previous = row[0]
                count += 1
        report['waveformRows'] = count
        report['lastSampleSeconds'] = previous
        if not report['solverDiagnostic'] and (not count or abs(previous-stop) > 1e-15):
            raise ValueError('Incomplete replay waveform')
        report['completed'] = process.returncode == 0 and not report['solverDiagnostic']
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        report['artifacts'] = {name: sha(out/name) for name in
                               ('io.cir', 'ngspice.log', 'trace.txt', 'host-trace.txt',
                                'driver-trace.txt', 'boundary-trace.txt') if (out/name).exists()}
        (out/'report.json').write_text(json.dumps(report, indent=2)+'\n')
    print(out/'report.json')


if __name__ == '__main__':
    main()
