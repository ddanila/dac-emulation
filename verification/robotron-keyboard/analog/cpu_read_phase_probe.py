#!/usr/bin/env python3
"""Demonstrate TV80's non-M1 operand sampling edge with an executed instruction."""
import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=ROOT / 'build/keyboard-controller-analog/cpu-read-phase')
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    tv80 = ROOT / 'third_party/cpu/tv80'
    source = json.loads((tv80 / 'SOURCE.json').read_text())
    for name, digest in source['files'].items():
        if sha(tv80 / name) != digest:
            raise ValueError('TV80 source differs: ' + name)
    report = {'passed': False, 'qualified': False, 'scope': __doc__, 'tv80': source,
              'fixtureSha256': sha(HERE / 'cpu_read_phase_probe.v'),
              'runnerSha256': sha(Path(__file__)),
              'boundary': 'A phase diagnostic of unmodified TV80, not a corrected U880 wrapper or calibrated pin timing.'}
    try:
        subprocess.run(['iverilog', '-g2012', '-s', 'probe', '-o', str(out / 'probe.vvp'),
                        *map(str, sorted(tv80.glob('*.v'))), str(HERE / 'cpu_read_phase_probe.v')], check=True)
        run = subprocess.run(['vvp', str(out / 'probe.vvp')], cwd=out, capture_output=True,
                             text=True, timeout=30)
        (out / 'simulation.log').write_text(run.stdout + run.stderr)
        run.check_returncode()
        def event(name, pattern):
            values = re.findall('^' + name + ' ' + pattern + '$', run.stdout, re.M)
            if len(values) != 1:
                raise ValueError('Missing or ambiguous event: ' + name)
            return values[0]
        rise, early = event('OPERAND_RISE', r'(\d+) ([0-9a-f]{2})')
        change = event('OPERAND_CHANGE', r'(\d+)')
        fall, late, captured = event('OPERAND_FALL', r'(\d+) ([0-9a-f]{2}) ([0-9a-f]{2})')
        written, address, output = event('OUTPUT', r'(\d+) ([0-9a-f]{4}) ([0-9a-f]{2})')
        if not (int(rise) < int(change) < int(fall) < int(written)):
            raise ValueError('Invalid phase event order')
        if (early, late, captured, address, output) != ('12', '34', '12', '1280', '12'):
            raise ValueError('Unexpected instruction-level sampling behavior')
        setup_ns = (int(fall) - int(change)) / 1000
        if setup_ns < 60 or 'READ_PHASE_DIAGNOSTIC_PASS' not in run.stdout:
            raise ValueError('Insufficient falling-edge setup or incomplete fixture')
        report.update(passed=True, risingEdgeValue=early, fallingEdgeValue=late,
                      capturedValue=captured, instructionOutput=output, fallingEdgeSetupNs=setup_ns,
                      reference={'url': 'https://www.tiffe.de/robotron/Bausteinuebersicht/U880D-CPU.pdf',
                                 'sha256': 'a3266f1cea4d24c0c91ca2941f6b40762f24a2934e6cf41dccd5fb52f80e75be',
                                 'page': 'Printed 58, PDF 59', 'nonM1SetupNs': 60},
                      files={name: sha(out / name) for name in ('probe.vvp', 'simulation.log')})
        report['iverilog'] = subprocess.run(['iverilog', '-V'], capture_output=True,
                                            text=True, check=True).stdout.splitlines()[0]
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
