#!/usr/bin/env python3
"""Review retained MPFR trial equations and final truncation without rerunning SPICE."""
import argparse
from fractions import Fraction
import importlib.util
import json
import math
from pathlib import Path
import re
import sys

ANALOG = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ANALOG))
from analog_driver_replay import sha
from linear_system_review import parse, review
from linear_precision_review import solve
from truncation_arithmetic_review import review_record

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('run', type=Path)
parser.add_argument('--out', type=Path, required=True)
args = parser.parse_args()
parent = json.loads((args.run/'report.json').read_text())
if parent['mode'] not in ('256','512') or parent['precisionGuardDiagnostics']:
    raise ValueError('Expected active MPFR run without guard rejection')
for name, digest in parent['artifacts'].items():
    if sha(args.run/name) != digest: raise ValueError('Input differs: '+name)
log = (args.run/'ngspice.log').read_text()
deck = (args.run/'io.cir').read_text()
# Restrict this review to the matched strict trapezoidal fixture.
if re.search(r'\bmethod\s*=', deck, re.I): raise ValueError('Explicit integration method not admitted')
abstol = re.findall(r'\babstol=([0-9.eE+-]+)', deck)
if len(abstol) != 1: raise ValueError('Ambiguous abstol')
trtol_values = re.findall(r'\btrtol=([0-9.eE+-]+)', deck)
if trtol_values != ['1']: raise ValueError('Expected explicit matched trtol=1')
trtol = 1.0
state_parser = ANALOG/'reports/host-reference-state-audit/run.py'
spec = importlib.util.spec_from_file_location('retained_state_parser',state_parser)
module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
state = module.summarize(log)
last = state['lastTrials'][-1]
records = [dict(re.findall(r'(\w+)=([^\s]+)', line)) for line in log.splitlines()
           if line.startswith('TRUNC_AUDIT error ')]
records = [r for r in records if float.fromhex(r['time']) == last['timeSeconds'] and
           float.fromhex(r['delta']) == last['deltaSeconds']]
if not records or last['truncation'] is None: raise ValueError('No final truncation evidence')
truncation = [review_record(r,float(abstol[0]),trtol) for r in records]
systems, incomplete = parse(log)
if incomplete: raise ValueError('Incomplete equation audit')
linear = []
for system in systems:
    reference = solve(system,160)
    differences = {i:abs(system['x'][i]-reference[i])/max(Fraction(1),abs(reference[i])) for i in reference}
    linear.append({'residualReview':review(system),
        'maximumScaledDifferenceFromDecimal160':float(max(differences.values()))})
companion = []
for item in last['inductors']:
    if item['order'] != 2: raise ValueError('Companion review requires trapezoidal order 2')
    exact = (Fraction(item['ag0'])*(Fraction(item['flux0'])-Fraction(item['flux1']))
             - Fraction(item['ag1'])*Fraction(item['volt1']))
    companion.append({'name':item['name'], 'loggedIntegratedVoltage':item['volt0'],
        'exactHistoryIntegratedVoltage':float(exact),
        'integrationArithmeticDifferenceV':float(Fraction(item['volt0'])-exact),
        'solvedBranchVoltage':item['vp']-item['vn'],
        'branchMinusExactHistoryVoltage':float(Fraction(item['vp'])-Fraction(item['vn'])-exact)})
result = {'qualified':False,'scope':__doc__,'sourceReportSha256':sha(args.run/'report.json'),
 'inputLogSha256':sha(args.run/'ngspice.log'),
 'sources':{str(p.relative_to(ANALOG)):sha(p) for p in [Path(__file__),state_parser,
    ANALOG/'linear_system_review.py',ANALOG/'linear_precision_review.py',ANALOG/'truncation_arithmetic_review.py',
    ANALOG/'analog_driver_replay.py']},
 'state':state,'finalInductorCompanions':companion,'linearSystems':linear,'finalTruncationArithmetic':truncation,
 'finalTimeResolution':{'timeUlpSeconds':math.ulp(last['timeSeconds']),
    'trialDeltaInTimeUlps':last['deltaSeconds']/math.ulp(last['timeSeconds']),
    'proposedDeltaInTimeUlps':last['truncation']['proposed']/math.ulp(last['timeSeconds'])},
 'boundary':'Logged trial states may be rejected. Decimal agreement checks stamped equations, not nonlinear model validity or state-history accuracy. Exact truncation arithmetic preserves already rounded state histories; near-time-resolution proposals are not repaired by this analysis. Companion voltage differences include state rounding, stamping and Newton state lag; they do not isolate one cause.'}
args.out.write_text(json.dumps(result,indent=2)+'\n')
print(args.out)
