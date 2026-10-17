#!/usr/bin/env python3
"""Check switch threshold plateaus; this is a solver regression, not board qualification."""
import argparse
import hashlib
import json
import math
import subprocess
import shutil
from pathlib import Path
from failure_evidence import solver_diagnostic


def run(engine, out):
    out.mkdir(parents=True, exist_ok=True)
    report = {'passed': False, 'scope': __doc__, 'runs': [],
              'criterion': 'At zero hysteresis, an exact threshold plateau retains the preceding state, as in the nonnegative-hysteresis branch.',
              'ngspice': subprocess.check_output([engine, '--version'], text=True),
              'ngspiceSha256': hashlib.sha256(Path(shutil.which(engine)).read_bytes()).hexdigest(),
              'sources': {name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                          for name in ('switch_boundary_probe.py', 'failure_evidence.py')}}
    for label, width, states in [('zero', 0, [False, True, True, False]),
                                 ('positive', .1, [False, True, True, False]),
                                 ('negative', -.1, [True, True, False, False])]:
        directory = out / label
        directory.mkdir(exist_ok=True)
        deck = f'''Switch state boundary regression: {label}
Vcc supply 0 5
Vcontrol control 0 PWL(0 0 1n 0 2n 2.5 20n 2.5 21n 5 40n 5 41n 2.5 60n 2.5 61n 0)
Rpull supply output 1k
Sdriver output 0 control 0 switchmodel
.model switchmodel SW(RON=20 ROFF=1t VT=2.5 VH={width})
.options reltol=1e-7 vntol=1e-9 abstol=1e-15
.control
set wr_singlescale
set wr_vecnames
set numdgt=17
tran .1n 90n
wrdata trace.txt v(control) v(output)
quit
.endc
.end
'''
        (directory / 'probe.cir').write_text(deck)
        (directory / 'trace.txt').unlink(missing_ok=True)
        with (directory / 'ngspice.log').open('w') as log:
            proc = subprocess.run([engine, '-n', '-b', 'probe.cir'], cwd=directory,
                                  stdout=log, stderr=subprocess.STDOUT, timeout=30)
        diagnostic = solver_diagnostic((directory / 'ngspice.log').read_text())
        item = {'hysteresisVolts': width, 'exitCode': proc.returncode,
                'solverDiagnostic': diagnostic, 'passed': False}
        if proc.returncode == 0 and not diagnostic:
            rows = [list(map(float, line.split())) for line in
                    (directory / 'trace.txt').read_text().splitlines()[1:]]
            if (not rows or any(len(row) != 3 or not all(map(math.isfinite, row)) for row in rows)
                    or any(a[0] > b[0] for a, b in zip(rows, rows[1:]))
                    or rows[0][0] > 1e-12 or abs(rows[-1][0] - 90e-9) > 1e-15):
                raise ValueError('Invalid switch regression waveform')
            item['plateaus'] = []
            for (start, stop), on in zip([(5, 15), (25, 35), (45, 55), (70, 80)], states):
                values = [row[2] for row in rows if start * 1e-9 <= row[0] <= stop * 1e-9]
                expected = 5 * 20 / 1020 if on else 5 * 1e12 / (1e12 + 1000)
                error = max(abs(v - expected) for v in values) if values else None
                item['plateaus'].append({'windowNs': [start, stop], 'expectedOn': on,
                                         'samples': len(values), 'maximumVoltageError': error,
                                         'passed': error is not None and error < 1e-6})
            item['passed'] = all(check['passed'] for check in item['plateaus'])
        item['artifacts'] = {name: hashlib.sha256((directory / name).read_bytes()).hexdigest()
                             for name in ('probe.cir', 'ngspice.log', 'trace.txt') if (directory / name).exists()}
        report['runs'].append(item)
    report['passed'] = all(item['passed'] for item in report['runs'])
    (out / 'report.json').write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ngspice', default='ngspice')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    result = run(args.ngspice, args.out.resolve())
    print(json.dumps({'passed': result['passed'], 'runs': [(r['hysteresisVolts'], r['passed']) for r in result['runs']]}))
    raise SystemExit(0 if result['passed'] else 1)
