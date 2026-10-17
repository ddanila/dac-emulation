#!/usr/bin/env python3
"""Qualify an existing BR service scenario pair without rerunning its simulations."""
import argparse
import json
import math
import subprocess
import sys
from pathlib import Path

from compare_firmware_io import sha

HERE = Path(__file__).resolve().parent


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('coarse', type=Path)
    p.add_argument('fine', type=Path)
    p.add_argument('--scenario', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--timeout-seconds', type=float, default=300, help='Wall-clock limit for each validation phase, including waveform decoding')
    args = p.parse_args()
    if not math.isfinite(args.timeout_seconds) or args.timeout_seconds <= 0:
        p.error('timeout-seconds must be positive and finite')
    args.out.mkdir(parents=True, exist_ok=True)
    report = {'passed': False, 'scope': __doc__, 'checks': [],
              'limits': {'edgeConvergenceNs': 15, 'sampledSetupHoldNs': 100, 'validationTimeoutSeconds': args.timeout_seconds},
              'qualificationBoundary': 'Selected BR service fixture; not electrical oscillator/reset, brownout or specimen calibration',
              'sources': {name: sha(HERE / name) for name in (
                  'qualify_io_pair.py', 'compare_firmware_io.py', 'failure_evidence.py', 'scenario_coverage.py',
                  'receiver_margins.py', 'io_scenario.py', 'serial_observation.py', 'reset_observation.py', 'led_observation.py', 'trace_io.py', 'compare_led_reference.py', 'firmware_io_reference.c')}}
    try:
        inputs = {'coarse': args.coarse / 'report.json', 'fine': args.fine / 'report.json', 'scenario': args.scenario}
        report['inputs'] = {name: {'path': str(path.resolve()), 'sha256': sha(path)} for name, path in inputs.items()}
        phases = [('convergence', 'compare_firmware_io.py', [args.coarse, args.fine, '--tolerance-ns', '15'])]
        for name, directory in [('coarse', args.coarse), ('fine', args.fine)]:
            phases.extend([
                (name + '-coverage', 'scenario_coverage.py', [directory, '--scenario', args.scenario]),
                (name + '-margins', 'receiver_margins.py', [directory, '--required-ns', '100'])])
        for name, directory in [('coarse', args.coarse), ('fine', args.fine)]:
            if json.loads((directory / 'report.json').read_text())['assumptions'].get('ledTrace'):
                phases.append((name + '-led-reference', 'compare_led_reference.py', [directory]))
        for name, script, options in phases:
            output = args.out / (name + '.json')
            output.unlink(missing_ok=True)
            process = subprocess.run([sys.executable, str(HERE / script), *map(str, options), '--out', str(output)],
                                     capture_output=True, text=True, timeout=args.timeout_seconds)
            (args.out / (name + '.log')).write_text(process.stdout + process.stderr)
            check = {'name': name, 'exitCode': process.returncode, 'report': output.name,
                     'reportSha256': sha(output) if output.exists() else None}
            report['checks'].append(check)
            if process.returncode != 0 or not output.exists() or json.loads(output.read_text()).get('passed') is not True:
                raise ValueError('Qualification check failed: ' + name)
        for name, path in inputs.items():
            if sha(path) != report['inputs'][name]['sha256']:
                raise ValueError('Qualification input changed during checks: ' + name)
        report['passed'] = True
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        (args.out / 'qualification.json').write_text(json.dumps(report, indent=2) + '\n')
    print(args.out / 'qualification.json')


if __name__ == '__main__':
    main()
