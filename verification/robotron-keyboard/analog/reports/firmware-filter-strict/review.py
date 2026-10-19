#!/usr/bin/env python3
"""Verify matched failed firmware captures differing only in winding coupling."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

ANALOG = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ANALOG))
from failure_evidence import solver_diagnostic


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(directory):
    report = json.loads((directory / 'report.json').read_text())
    if report['passed'] is not False:
        raise ValueError('Expected a failed capture, not a qualification input')
    for name, receipt in report['failureArtifacts'].items():
        if receipt['status'] == 'retained':
            path = directory / name
            if path.stat().st_size != receipt['bytes'] or sha(path) != receipt['sha256']:
                raise ValueError('Failure artifact differs: ' + name)
    if sha(directory / 'io.cir') != report['deckSha256']:
        raise ValueError('Deck differs')
    diagnostic = solver_diagnostic((directory / 'ngspice.log').read_text())
    if not diagnostic or 'timestep too small' not in diagnostic.lower():
        raise ValueError('Expected retained timestep rejection')
    traces = {}
    for name, columns in [('trace.txt', 3), ('host-trace.txt', 7), ('driver-trace.txt', 2)]:
        first = previous = None
        count = 0
        with (directory / name).open() as stream:
            if len(next(stream).split()) != columns:
                raise ValueError('Invalid trace header')
            for line in stream:
                row = list(map(float, line.split()))
                if len(row) != columns or not all(map(math.isfinite, row)):
                    raise ValueError('Invalid trace row')
                if previous is not None and row[0] < previous:
                    raise ValueError('Backward trace')
                if first is None:
                    first = row[0]
                previous = row[0]
                count += 1
        if not count or first != 0:
            raise ValueError('Missing startup samples')
        traces[name] = {'rows': count, 'lastSampleSeconds': previous,
                        'sha256': sha(directory / name)}
    return report, {'reportSha256': sha(directory / 'report.json'),
                    'solverDiagnostic': diagnostic, 'traces': traces}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('control', type=Path)
    parser.add_argument('coupled', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    a, ar = load(args.control)
    b, br = load(args.coupled)
    for key in ('sources', 'ngspiceRuntime', 'romSha256', 'connectivitySha256',
                'bridge', 'tv80', 'cReferenceSources', 'referenceLogSha256'):
        if a[key] != b[key]:
            raise ValueError('Different provenance: ' + key)
    hdl = [{Path(name).name: digest for name, digest in r['hdlSha256'].items()} for r in (a, b)]
    if hdl[0] != hdl[1] or any(len(h) != len(r['hdlSha256']) for h, r in zip(hdl, (a, b))):
        raise ValueError('HDL inputs differ or names are ambiguous')
    for report, coupling in ((a, 0), (b, .8)):
        f = report['assumptions']['filterHypothesis']
        if f['coupling'] != coupling or set(f['dotPins'].values()) != {1} or f['qualified']:
            raise ValueError('Unexpected filter hypothesis')
    aa, ba = (dict(r['assumptions']) for r in (a, b))
    af, bf = (dict(v.pop('filterHypothesis')) for v in (aa, ba))
    af.pop('coupling'); bf.pop('coupling')
    if aa != ba or af != bf:
        raise ValueError('Other fixture assumptions differ')
    control = (args.control / 'io.cir').read_text().splitlines()
    coupled = (args.coupled / 'io.cir').read_text().splitlines()
    added = [line for line in coupled if line.startswith('Kfilter')]
    expected = [f'Kfilter{i}{j} L1.{i} L1.{j} 0.80000000000000004'
                for i in range(1, 5) for j in range(i + 1, 5)]
    if added != expected or control != [line for line in coupled if not line.startswith('Kfilter')]:
        raise ValueError('Decks differ beyond the declared coupling')
    result = {'completed': True, 'qualified': False, 'scope': __doc__,
              'reviewerSha256': sha(Path(__file__)),
              'diagnosticScannerSha256': sha(ANALOG / 'failure_evidence.py'),
              'control': ar, 'coupled': br, 'onlyDeckChanges': added,
              'interpretation': 'Both coupled-firmware captures fail before the scenario endpoint. The coupling hypothesis changes the trajectory but does not remedy the strict-tolerance failure. This is a model-sensitivity control, not timestep convergence or identification of physical winding parameters.'}
    args.out.write_text(json.dumps(result, indent=2) + '\n')
    print(args.out)


if __name__ == '__main__':
    main()
