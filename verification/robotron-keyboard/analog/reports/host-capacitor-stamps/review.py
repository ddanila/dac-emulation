#!/usr/bin/env python3
"""Review capacitor arithmetic/assembly in the reproduced final linear system."""
import argparse
from fractions import Fraction as F
import importlib.util
import json
from pathlib import Path
import re
import sys

ANALOG = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ANALOG))
from analog_driver_replay import sha
from capacitor_stamp_review import parse as parse_capacitors, corrections
from linear_system_review import parse, review
from linear_precision_review import solve

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('run', type=Path)
parser.add_argument('--out', type=Path, required=True)
args = parser.parse_args()
parent = json.loads((args.run/'report.json').read_text())
control = json.loads((args.run/'audit-control.json').read_text())
if not control['reproducedEvidence'] or control['reportSha256'] != sha(args.run/'report.json'):
    raise ValueError('Missing matched logging control')
for name, digest in parent['artifacts'].items():
    if sha(args.run/name) != digest:
        raise ValueError('Changed input: '+name)
if re.search(r'\bmethod\s*=', (args.run/'io.cir').read_text(), re.I):
    raise ValueError('Only original trapezoidal integration admitted')
log = (args.run/'ngspice.log').read_text()
systems, incomplete = parse(log)
if incomplete:
    raise ValueError('Incomplete linear audit')
capacitors = parse_capacitors(log)
state_parser = ANALOG/'reports/host-reference-state-audit/run.py'
spec = importlib.util.spec_from_file_location('state_audit', state_parser)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
trial = module.summarize(log)['lastTrials'][-1]
system = systems[-1]
if (trial['newtonResult'] != 0 or trial['timeSeconds'] != float.fromhex(system['metadata']['time'])
        or trial['deltaSeconds'] != float.fromhex(system['metadata']['delta'])
        or trial['order'] != int(system['metadata']['order'])):
    raise ValueError('Missing final converged trial system')
for name, values in trial['nodes'].items():
    index = next((i for i,n in system['names'].items() if n == name), None)
    if index is None and name == 'board_reference' and values['rhs'] == 0:
        continue
    if index is None or float(system['x'][index]) != values['rhs']:
        raise ValueError('Different final trial solution: '+name)
da, db, observations = corrections(capacitors[system['id']])
a, b = dict(system['a']), dict(system['b'])
for key, value in da.items():
    a[key] = a.get(key, F(0))+value
for key, value in db.items():
    b[key] = b.get(key, F(0))+value
corrected = dict(system, a=a, b=b)
original160, corrected160 = solve(system, 160), solve(corrected, 160)
original80, corrected80 = solve(system, 80), solve(corrected, 80)
scaled = lambda x,y: float(max(abs(x[i]-v)/max(F(1),abs(v)) for i,v in y.items()))
result = {'qualified': False, 'scope': __doc__, 'systemId': system['id'],
          'inputReportSha256': sha(args.run/'report.json'),
          'auditControlSha256': sha(args.run/'audit-control.json'),
          'sources': {str(p.relative_to(ANALOG)): sha(p) for p in
                      [Path(__file__), state_parser, ANALOG/'capacitor_stamp_review.py',
                       ANALOG/'linear_system_review.py', ANALOG/'linear_precision_review.py',
                       ANALOG/'analog_driver_replay.py']},
          'capacitors': observations,
          'matrixCorrections': [{'row':i,'column':j,'exactSiemens':str(v)} for (i,j),v in sorted(da.items()) if v],
          'rhsCorrections': [{'row':i,'exactAmps':str(v)} for i,v in sorted(db.items()) if v],
          'originalResiduals': review(system),
          'correctedResiduals': review(dict(corrected, x=corrected160)),
          'referenceNumerics': {'scaling':'Difference divided by max(1, abs(Decimal160 coordinate)); not a physical budget',
                               'original80Vs160': scaled(original80, original160),
                               'corrected80Vs160': scaled(corrected80, corrected160),
                               'recordedVs160': scaled(system['x'], original160)},
          'solutionChangesFromDecimal160Original': {system['names'][i]:float(corrected160[i]-v)
                                                   for i,v in original160.items()},
          'boundary': 'Frozen-equation diagnostic. Corrections replace each logged capacitor addition with exact rational integration/history contributions. '
                      'All other assembled terms, including subsequent rounding and nonlinear-device capacitances, remain fixed. '
                      'Previously rounded charge histories and coefficients remain inputs. No transient convergence or physical calibration claim.'}
args.out.write_text(json.dumps(result, indent=2)+'\n')
print(args.out)
