#!/usr/bin/env python3
"""Compare logged inductor integration arithmetic with exact rational history."""
import argparse
from fractions import Fraction
import importlib.util
import json
from pathlib import Path
import re
import sys

ANALOG = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ANALOG))
from analog_driver_replay import sha
from linear_system_review import parse, review

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('run',type=Path)
parser.add_argument('--out',type=Path,required=True)
args=parser.parse_args()
parent=json.loads((args.run/'report.json').read_text())
if parent.get('integrationArithmetic')!='256' or parent.get('completed'):
    raise ValueError('Expected a failed active integration replay')
for name,digest in parent['artifacts'].items():
    if sha(args.run/name)!=digest:raise ValueError('Input differs: '+name)
if re.search(r'\bmethod\s*=',(args.run/'io.cir').read_text(),re.I):
    raise ValueError('Only the original trapezoidal fixture is admitted')
state_parser=ANALOG/'reports/host-reference-state-audit/run.py'
spec=importlib.util.spec_from_file_location('retained_state_parser',state_parser)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
log=(args.run/'ngspice.log').read_text()
state=module.summarize(log)
last=state['lastTrials'][-1]
companions=[]
for item in last['inductors']:
    if item['order']==1:
        exact=Fraction(item['ag0'])*Fraction(item['flux0'])+Fraction(item['ag1'])*Fraction(item['flux1'])
    elif item['order']==2:
        exact=Fraction(item['ag0'])*(Fraction(item['flux0'])-Fraction(item['flux1']))-Fraction(item['ag1'])*Fraction(item['volt1'])
    else:raise ValueError('Unsupported logged integration order')
    companions.append({'name':item['name'],'loggedDerivative':item['volt0'],
                       'correctlyRoundedExactHistoryDerivative':float(exact),
                       'matchesExactHistoryRounding':item['volt0']==float(exact),
                       'differenceFromExact':float(Fraction(item['volt0'])-exact)})
systems,incomplete=parse(log)
if incomplete:raise ValueError('Incomplete linear audit')
result={'qualified':False,'sourceReportSha256':sha(args.run/'report.json'),
        'sources':{str(p.relative_to(ANALOG)):sha(p) for p in
                   (Path(__file__),state_parser,ANALOG/'linear_system_review.py',ANALOG/'analog_driver_replay.py')},
        'state':state,'finalInductorArithmetic':companions,
        'linearResiduals':[review(system) for system in systems],
        'boundary':'Exact arithmetic on logged binary64 histories checks the local integration operation only. It does not recover discarded history precision, establish accurate nonlinear states, or turn rejected trial voltages into physical predictions.'}
args.out.write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({'matchesExactHistoryRounding':all(x['matchesExactHistoryRounding'] for x in companions),
                  'lastNewtonResult':last['newtonResult'],'truncation':last['truncation']}))
