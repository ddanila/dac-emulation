#!/usr/bin/env python3
"""Check actual runtime mode admission and a constant-current capacitor solution."""
import argparse
import json
import math
from pathlib import Path
import re
import subprocess
import sys

ANALOG = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ANALOG))
from analog_driver_replay import sha
from ngspice_runtime import identify, verify
from failure_evidence import solver_diagnostic

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--runtime', type=Path, required=True)
parser.add_argument('--spinit', type=Path, required=True)
parser.add_argument('--out', type=Path, required=True)
args = parser.parse_args()
runtime, environment = identify(args.runtime, args.spinit)
args.out.mkdir(parents=True, exist_ok=False)
deck = '''Constant current capacitor: V(out) = time
I1 0 out 1
C1 out 0 1 IC=0
.tran .01 1 UIC
.control
set numdgt=17
set wr_singlescale
set wr_vecnames
run
wrdata trace.txt v(out)
quit
.endc
.end
'''
result = {'qualified': False, 'completed': False, 'runtime': runtime,
          'checkerSha256': sha(__file__), 'checks': {},
          'boundary': 'Analytic adapter smoke check, not stiff-circuit convergence or event/shared-runtime qualification.'}
verify(runtime)
for mode in ('unset', 'off', 'rollback', 'represented', 'invalid'):
    run = args.out/mode
    run.mkdir()
    (run/'check.cir').write_text(deck)
    env = dict(environment, ROBOTRON_MPFR_BITS='off', ROBOTRON_MPFR_INTEGRATION='off')
    env.pop('ROBOTRON_TIME_STEP', None)
    if mode != 'unset':
        env['ROBOTRON_TIME_STEP'] = mode
    process = subprocess.run([str(args.runtime.resolve()), '-n', '-b', 'check.cir'],
                             cwd=run, env=env, capture_output=True, text=True, timeout=60)
    log = process.stdout+process.stderr
    (run/'ngspice.log').write_text(log)
    record = {'exitCode': process.returncode, 'logSha256': sha(run/'ngspice.log'),
              'deckSha256': sha(run/'check.cir')}
    if mode == 'invalid':
        if 'TIME_STEP error invalid mode' not in log or (run/'trace.txt').exists():
            raise ValueError('Invalid mode was not rejected')
        record['invalidModeRejected'] = True
    else:
        expected = 'off' if mode == 'unset' else mode
        if re.findall(r'^TIME_STEP mode=(\w+)$', log, re.M) != [expected]:
            raise ValueError('Mode not confirmed: '+mode)
        if process.returncode or solver_diagnostic(log):
            raise ValueError('Unexpected runtime diagnostic: '+mode)
        lines = (run/'trace.txt').read_text().splitlines()
        if lines[0].split() != ['time', 'v(out)']:
            raise ValueError('Trace header differs')
        rows = [list(map(float, line.split())) for line in lines[1:]]
        if not rows or any(len(r) != 2 or not all(map(math.isfinite, r)) for r in rows):
            raise ValueError('Invalid trace')
        if any(b[0] <= a[0] for a,b in zip(rows, rows[1:])) or abs(rows[-1][0]-1) > 1e-15:
            raise ValueError('Incomplete or nonmonotonic trace')
        error = max(abs(t-v) for t,v in rows)
        if error > 1e-12:
            raise ValueError('Analytic solution differs')
        record.update(maximumAbsoluteErrorV=error, traceSha256=sha(run/'trace.txt'))
    result['checks'][mode] = record
verify(runtime)
if result['checks']['unset']['traceSha256'] != result['checks']['off']['traceSha256']:
    raise ValueError('Explicitly disabled mode differs from default')
result['completed'] = True
(args.out/'report.json').write_text(json.dumps(result, indent=2)+'\n')
print(args.out/'report.json')
