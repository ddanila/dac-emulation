#!/usr/bin/env python3
"""Exercise canonical latch/flip-flop pullups with independent nominal sink stimuli."""
import argparse
import json
import math
import os
from pathlib import Path
import shutil
import subprocess

from circuit import load
from logic_control import wiring
from clock_output_probe import sha
from failure_evidence import solver_diagnostic

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ngspice', default='ngspice')
    parser.add_argument('--out', type=Path, default=ROOT / 'build/keyboard-controller-analog/logic-control')
    args = parser.parse_args()
    found = shutil.which(args.ngspice)
    if found is None:
        parser.error('ngspice executable not found')
    engine = Path(found).resolve()
    components, connectivity = load()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    (out / 'spinit').write_text('* Pure SPICE logic-control fixture.\n')
    report = {'passed': False, 'qualified': False, 'scope': __doc__, 'cases': [],
              'boundary': 'Nominal sinks and illustrative loads; not a DL003/latch/flip-flop characterization or firmware co-simulation',
              'connectivitySha256': connectivity, 'executable': {'path': str(engine), 'sha256': sha(engine)},
              'spinitSha256': sha(out / 'spinit'),
              'sources': {name: sha(HERE / name) for name in ('logic_control_probe.py', 'logic_control.py', 'circuit.py', 'clock_output_probe.py', 'failure_evidence.py')}}
    try:
        for capacitance in (0, 10):
            directory = out / f'load-{capacitance}pf'
            directory.mkdir()
            lines, _, info = wiring(components, capacitance)
            nets = info['nets']
            signals = ' '.join(f'v({nets[name]})' for name in ('latchEnable', 'flipFlopRelease', 'ioActive'))
            deck = '\n'.join([
                'Nominal logic-control fixture', f'Vcc {nets["supply"]} {nets["ground"]} 5', *lines,
                'Venable control_latchEnable_sink 0 PWL(0 0 200n 0 201n 5 400n 5 401n 0 2u 0)',
                'Vio control_ioActive_sink 0 PWL(0 0 600n 0 601n 5 800n 5 801n 0 2u 0)',
                '.control', 'set wr_singlescale', 'set wr_vecnames', 'set numdgt=17',
                'tran .25n 2u', 'wrdata trace.txt ' + signals, 'quit', '.endc', '.end', ''])
            (directory / 'probe.cir').write_text(deck)
            result = subprocess.run([str(engine), '-n', '-b', 'probe.cir'], cwd=directory,
                                    env=dict(os.environ, SPICE_SCRIPTS=str(out)),
                                    capture_output=True, text=True, timeout=60)
            log = result.stdout + result.stderr
            (directory / 'ngspice.log').write_text(log)
            result.check_returncode()
            if solver_diagnostic(log):
                raise ValueError('Control fixture solver diagnostics')
            rows = [list(map(float, line.split())) for line in (directory / 'trace.txt').read_text().splitlines()[1:]]
            if not rows or any(len(row) != 4 or not all(map(math.isfinite, row)) for row in rows):
                raise ValueError('Invalid control waveform')
            if rows[0][0] > 1e-12 or abs(rows[-1][0] - 2e-6) > 1e-12:
                raise ValueError('Incomplete control waveform')
            windows = {'released': (1.2e-6, 1.9e-6, [5, 5, 5]),
                       'latchSink': (300e-9, 390e-9, [5 * 20 / 1020, 5, 5]),
                       'ioSink': (700e-9, 790e-9, [5, 5, 5 * 20 / 3920])}
            for name, (start, stop, expected) in windows.items():
                samples = [row[1:] for row in rows if start <= row[0] <= stop]
                if not samples or any(abs(v - target) > .001 for row in samples for v, target in zip(row, expected)):
                    raise ValueError('Unexpected control voltage: ' + name)
            recovery = next(row[0] for row in rows if row[0] > 800e-9 and row[3] > 2)
            report['cases'].append({'fixture': info, 'firstIoSampleAbove2VAfterReleaseSeconds': recovery,
                                    'deckSha256': sha(directory / 'probe.cir'), 'traceSha256': sha(directory / 'trace.txt'),
                                    'logSha256': sha(directory / 'ngspice.log')})
        delay = (report['cases'][1]['firstIoSampleAbove2VAfterReleaseSeconds'] -
                 report['cases'][0]['firstIoSampleAbove2VAfterReleaseSeconds']) * 1e9
        report['fixtureLoadAddedRecoveryNs'] = delay
        if delay < 10 or sha(engine) != report['executable']['sha256']:
            raise ValueError('Load effect absent or executable changed')
        report['passed'] = True
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(out / 'report.json')


if __name__ == '__main__':
    main()
