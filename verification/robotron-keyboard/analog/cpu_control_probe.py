#!/usr/bin/env python3
"""Exercise the CPU control pullups and an external X1:A9 service sink."""
import argparse
import json
import math
import os
from pathlib import Path
import shutil
import subprocess

from circuit import load
from cpu_control import wiring
from clock_output_probe import sha
from failure_evidence import solver_diagnostic

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ngspice', default='ngspice')
    parser.add_argument('--out', type=Path, default=ROOT / 'build/keyboard-controller-analog/cpu-control')
    args = parser.parse_args()
    found = shutil.which(args.ngspice)
    if found is None:
        parser.error('ngspice executable not found')
    engine = Path(found).resolve()
    components, connectivity = load()
    lines, _, nets = wiring(components)
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    (out / 'spinit').write_text('* Pure SPICE CPU control fixture.\n')
    signals = ' '.join(f'v({nets[key]})' for key in ('interruptNmiWait', 'busRequest'))
    deck = '\n'.join([
        'CPU control pullups with illustrative external service sink',
        f'Vcc {nets["supply"]} {nets["ground"]} 5', *lines,
        'Vservice service 0 PWL(0 0 500n 0 501n 5 1u 5 1001n 0 2u 0)',
        f'Sservice {nets["busRequest"]} {nets["ground"]} service 0 CONTACT',
        '.model CONTACT SW(Ron=100 Roff=1e12 Vt=2.5 Vh=.1)',
        '.control', 'set wr_singlescale', 'set wr_vecnames', 'set numdgt=17',
        'tran .25n 2u', 'wrdata trace.txt ' + signals, 'quit', '.endc', '.end', ''])
    (out / 'probe.cir').write_text(deck)
    report = {'passed': False, 'qualified': False, 'scope': __doc__,
              'boundary': '5 V ideal supply and illustrative 100-ohm external sink; no CPU execution, leakage, clamps, brownout or switching calibration',
              'circuit': nets, 'connectivitySha256': connectivity,
              'sources': {name: sha(HERE / name) for name in ('cpu_control_probe.py', 'cpu_control.py', 'cpu_clock_limits.json', 'circuit.py', 'clock_output_probe.py', 'failure_evidence.py')},
              'executable': {'path': str(engine), 'sha256': sha(engine)},
              'spinitSha256': sha(out / 'spinit'), 'deckSha256': sha(out / 'probe.cir')}
    try:
        result = subprocess.run([str(engine), '-n', '-b', 'probe.cir'], cwd=out,
                                env=dict(os.environ, SPICE_SCRIPTS=str(out)),
                                capture_output=True, text=True, timeout=60)
        log = result.stdout + result.stderr
        (out / 'ngspice.log').write_text(log)
        result.check_returncode()
        if solver_diagnostic(log) or sha(engine) != report['executable']['sha256']:
            raise ValueError('Solver diagnostics or changed executable')
        rows = [list(map(float, line.split())) for line in (out / 'trace.txt').read_text().splitlines()[1:]]
        if not rows or any(len(row) != 3 or not all(map(math.isfinite, row)) for row in rows):
            raise ValueError('Invalid control waveform')
        if rows[0][0] > 1e-12 or abs(rows[-1][0] - 2e-6) > 1e-12:
            raise ValueError('Incomplete control waveform')
        if any(abs(row[1] - 5) > .001 for row in rows):
            raise ValueError('Service request disturbed interrupt/NMI/wait net')
        windows = {'releasedBefore': (100e-9, 400e-9, 5),
                   'asserted': (600e-9, 900e-9, 5 * 100 / 1100),
                   'releasedAfter': (1.2e-6, 1.9e-6, 5)}
        report['observations'] = {}
        for name, (start, stop, expected) in windows.items():
            samples = [row[2] for row in rows if start <= row[0] <= stop]
            if not samples or any(abs(value - expected) > .001 for value in samples):
                raise ValueError('Unexpected bus-request voltage: ' + name)
            report['observations'][name] = {'minimumVolts': min(samples), 'maximumVolts': max(samples)}
        report['traceSha256'], report['logSha256'] = sha(out / 'trace.txt'), sha(out / 'ngspice.log')
        report['passed'] = True
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(out / 'report.json')


if __name__ == '__main__':
    main()
