#!/usr/bin/env python3
"""Compare uncoupled trapezoidal inductor stamps with exact logged-history equations."""
import argparse
from fractions import Fraction as F
import json
from pathlib import Path
import re
import sys

ANALOG = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ANALOG))
from analog_driver_replay import sha
from linear_system_review import parse, review
from linear_precision_review import solve

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('run',type=Path)
parser.add_argument('--out',type=Path,required=True)
args=parser.parse_args()
parent=json.loads((args.run/'report.json').read_text())
for name in ['ngspice.log','io.cir']:
    if sha(args.run/name)!=parent['artifacts'][name]:raise ValueError('Changed input '+name)
state=json.loads((args.run/'state-review.json').read_text())
if state['inputLogSha256']!=sha(args.run/'ngspice.log'):raise ValueError('Different state audit')
trial=state['state']['lastTrials'][-1]
system=parse((args.run/'ngspice.log').read_text())[0][-1]
if (trial['order']!=2 or int(system['metadata']['order'])!=2 or
    trial['timeSeconds']!=float.fromhex(system['metadata']['time']) or
    trial['deltaSeconds']!=float.fromhex(system['metadata']['delta'])):
    raise ValueError('Expected matching final second-order trial')
deck=(args.run/'io.cir').read_text()
if re.search(r'^\s*[kK]\S*\s',deck,re.M) or re.search(r'\bmethod\s*=',deck,re.I):
    raise ValueError('Only uncoupled default-trapezoidal fixture admitted')
a=dict(system['a']);b=dict(system['b']);stamps=[]
for item in trial['inductors']:
    if item['order']!=2 or item['m']!=1:raise ValueError('Unsupported inductor mode')
    row_index=next(i for i,name in system['names'].items() if name==item['name']+'#branch')
    row={j:value for (i,j),value in a.items() if i==row_index}
    if row_index not in row or len(row) not in (2,3) or any(value not in (1,-1) for j,value in row.items() if j!=row_index):
        raise ValueError('Unexpected inductor row topology')
    diagonal=-F(item['ag0'])*F(item['L'])/F(item['m'])
    rhs=-F(item['ag1'])*F(item['volt1'])-F(item['ag0'])*F(item['flux1'])
    residual=sum(value*system['x'][j] for j,value in row.items())-b[row_index]
    coefficient_error=(row[row_index]-diagonal)*system['x'][row_index]
    rhs_error=b[row_index]-rhs
    stamps.append({'name':item['name'],'row':row_index,
        'rhsRoundingEquivalentV':float(rhs_error),
        'diagonalRoundingAtRecordedCurrentV':float(coefficient_error),
        'recordedEquationResidualV':float(residual),
        'exactHistoryEquationResidualV':float(residual-coefficient_error+rhs_error)})
    a[row_index,row_index]=diagonal;b[row_index]=rhs
corrected=dict(system,a=a,b=b)
original_reference=solve(system,160)
corrected_solution=solve(corrected,160)
changes={system['names'][i]:float(corrected_solution[i]-original_reference[i]) for i in corrected_solution}
result={'qualified':False,'scope':__doc__,'inputReportSha256':sha(args.run/'report.json'),
 'inputStateReviewSha256':sha(args.run/'state-review.json'),'systemId':system['id'],
 'sources':{str(p.relative_to(ANALOG)):sha(p) for p in [Path(__file__),ANALOG/'linear_system_review.py',ANALOG/'linear_precision_review.py']},
 'equations':{'diagonal':'-ag0 * L / m','rhs':'-ag1 * previous_voltage - ag0 * previous_flux',
              'basis':'ngspice NIintegrate trapezoidal order 2 and INDload, using exact rational products of logged binary64 inputs'},
 'stamps':stamps,'correctedFrozenSystemResiduals':review(dict(corrected,x=corrected_solution)),
 'solutionChangesFromDecimal160Original':changes,
 'boundary':'Frozen-equation diagnostic only. Previously rounded histories, device derivatives and integration coefficients remain inputs. Current and voltage coordinates have different units. Does not isolate an accumulated trajectory error or establish physical behavior.'}
args.out.write_text(json.dumps(result,indent=2)+'\n')
print(args.out)
