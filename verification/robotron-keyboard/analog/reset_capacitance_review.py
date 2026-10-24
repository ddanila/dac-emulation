#!/usr/bin/env python3
"""Compare source C4 alternatives; isolated exploratory reset, not board qualification."""
import argparse
from copy import deepcopy
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
from types import SimpleNamespace

from circuit import load
from reset_probe import simulate

HERE = Path(__file__).resolve().parent


def releases(rows, start, end, threshold=2):
    """Absolute-time upward crossings; never discard extra transitions."""
    return [a[0] + (threshold-a[3])*(b[0]-a[0])/(b[3]-a[3]) - start
            for a, b in zip(rows, rows[1:])
            if start <= a[0] < b[0] <= end and a[3] < threshold <= b[3]]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--ngspice', default='ngspice')
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--npn-profile', choices=('generic', 'sc236-dc'), default='generic')
    args = p.parse_args()
    executable = shutil.which(args.ngspice)
    if not executable:
        p.error('ngspice not found')
    executable = str(Path(executable).resolve())
    args.out.mkdir(parents=True, exist_ok=True)
    components, connectivity = load()
    if components['C4']['type'] != '10u':
        raise ValueError('Reference C4 changed; review the variant baseline')
    variants = json.loads((HERE/'reset-capacitance-sources.json').read_text())
    stimulus = {'pointsSecondsVolts': [[0, 0], [1e-6, 5], [3, 5],
                                      [3.000001, 0], [4, 0], [4.000001, 5], [7, 5]]}
    report = {'completed': False, 'qualified': False, 'scope': __doc__,
              'connectivitySha256': connectivity, 'variants': variants,
              'supplyStimulus': stimulus, 'runs': [],
              'runtime': {'executable': executable, 'sha256': digest(Path(executable)),
                          'version': subprocess.check_output([executable, '--version'], text=True)},
              'sources': {name: digest(HERE/name) for name in (
                  'reset_capacitance_review.py', 'reset-capacitance-sources.json',
                  'reset_probe.py', 'circuit.py', 'cpu_control.py', 'cpu_clock_limits.json',
                  'supply_stimulus.py', 'reset_supply_observation.py', 'sc236_dc.cir')},
              'assumptions': {'beta': 100, 'npnProfile': args.npn_profile,
                  'cpuLoad': 'reference-capacitance', 'sourceOhms': 0,
                  'passives': 'Ideal nominal values; no ESR, leakage or tolerance',
                  'semiconductors': 'Selected exploratory NPN profile; generic PNP and diode models',
                  'thresholdVolts': 2,
                  'boundary': 'Closed BR2, isolated reset circuit. No CPU execution, full-board convergence, installed-value identification or device admission.'}}
    try:
        for variant in variants['variants']:
            circuit = deepcopy(components)
            circuit['C4']['type'] = variant['spiceValue']
            for step in (100, 50):
                run_args = SimpleNamespace(out=args.out/variant['id'], ngspice=executable,
                    reset_load='reference-capacitance', rise_us=1, stop_seconds=7,
                    source_ohms=0, beta=100, npn_profile=args.npn_profile, supply_data=stimulus)
                run = simulate(run_args, circuit, step, False)
                directory = run_args.out/f'closed-{step}us'
                trace = directory/'trace.txt'
                rows = [[float(x) for x in line.split()] for line in trace.read_text().splitlines()[1:]]
                run.update(variant=variant['id'], directory=str(directory.relative_to(args.out)),
                           releasesSecondsAt2V=[releases(rows, a, b) for a,b in ((0,3),(4,7))])
                # Retain complete raw samples compressed, with deterministic gzip metadata.
                compressed = trace.with_suffix('.txt.gz')
                compressed.write_bytes(gzip.compress(trace.read_bytes(), mtime=0))
                run['compressedTraceSha256'] = digest(compressed)
                trace.unlink()
                report['runs'].append(run)
        comparisons = []
        for variant in variants['variants']:
            pair = [r for r in report['runs'] if r['variant'] == variant['id']]
            a,b = [r['releasesSecondsAt2V'] for r in pair]
            unique = all(len(window)==1 for run in (a,b) for window in run)
            deltas = [abs(x[0]-y[0]) for x,y in zip(a,b)] if unique else None
            comparisons.append({'variant':variant['id'], 'oneReleasePerPoweredWindow': unique,
                'releaseDifferenceSeconds': deltas,
                'releaseTimingWithin100us': unique and max(deltas) <= 100e-6})
        report['timingComparisons'] = comparisons
        if digest(Path(executable)) != report['runtime']['sha256']:
            raise ValueError('Simulator changed during comparison')
        for name, expected in report['sources'].items():
            if digest(HERE/name) != expected:
                raise ValueError('Source changed during comparison: ' + name)
        report['completed'] = True
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        (args.out/'assessment.json').write_text(json.dumps(report, indent=2)+'\n')
    print(args.out/'assessment.json')


if __name__ == '__main__':
    main()
