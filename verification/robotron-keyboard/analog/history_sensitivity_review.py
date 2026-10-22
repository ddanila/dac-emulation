#!/usr/bin/env python3
"""Frozen-system sensitivity to one rounding of stored capacitor history."""
import argparse
from fractions import Fraction as F
import json
import math
from pathlib import Path

from analog_driver_replay import sha
from capacitor_stamp_review import parse as caps_parse, corrections
from linear_system_review import parse
from linear_precision_review import solve

def sensitivity(system,group):
    da,db,_=corrections(group)
    matrix=dict(system['a'])
    for k,v in da.items():matrix[k]=matrix.get(k,F(0))+v
    names={n:i for i,n in system['names'].items()};data=names['n_cable_daten'];ground=names['host_receiver_gnd']
    n=int(system['metadata']['size']);rhs={i:F(int(i==data)-int(i==ground)) for i in range(1,n+1)}
    adjoint=dict(system,a={(j,i):v for (i,j),v in matrix.items()},b=rhs)
    low,high=solve(adjoint,80),solve(adjoint,160)
    relative=max(abs(low[i]-v)/max(F(1),abs(v)) for i,v in high.items())
    if relative>F('1e-40'):raise ValueError('Adjoint precision comparison failed')
    rows=[]
    for item in group['capacitors']:
        c=item['before'];response=high.get(c['p'],F(0))-high.get(c['n'],F(0))
        # RHS capacitor contribution at positive node is -history.
        qfactor=-F(c['m'])*F(c['ag1']) if group['order']==1 else F(c['m'])*F(c['ag0'])
        ifactor=F(0) if group['order']==1 else F(c['m'])*F(c['ag1'])
        qbound=abs(response*qfactor)*F(math.ulp(c['q1']))/2
        ibound=abs(response*ifactor)*F(math.ulp(c['i1']))/2
        rows.append({'name':c['name'],'chargeHistoryCoulombs':c['q1'],'currentHistoryAmps':c['i1'],'halfUlpChargeResponseV':float(qbound),'halfUlpCurrentResponseV':float(ibound)})
    rows.sort(key=lambda r:r['halfUlpChargeResponseV']+r['halfUlpCurrentResponseV'],reverse=True)
    return {'systemId':system['id'],'timeSeconds':float.fromhex(system['metadata']['time']),'deltaSeconds':float.fromhex(system['metadata']['delta']),'order':group['order'],'adjoint80Vs160Scaled':float(relative),'independentHalfUlpHistoryBoundV':sum(r['halfUlpChargeResponseV']+r['halfUlpCurrentResponseV'] for r in rows),'capacitors':rows}

def selected_log(path,ids):
    cap=[];latest=[];selected=[];active=False;collect=False
    with path.open() as stream:
        for line in stream:
            if line.startswith('CAP_AUDIT begin '):cap=[line];collect=True
            elif collect:
                cap.append(line)
                if line.strip()=='CAP_AUDIT end':latest=cap;collect=False
            if line.startswith('LINEAR_AUDIT begin '):
                fields=dict(x.split('=',1) for x in line.split()[2:]);active=int(fields['id']) in ids
                if active:selected.extend(latest)
            if active:selected.append(line)
            if line.startswith('LINEAR_AUDIT end '):active=False
    return ''.join(selected)

def main():
    p=argparse.ArgumentParser();p.add_argument('run',type=Path);p.add_argument('--onset',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    producer=json.loads((a.run/'report.json').read_text());onset=json.loads(a.onset.read_text())
    if onset['sourceReportSha256']!=sha(a.run/'report.json') or producer['artifacts']['ngspice.log']!=sha(a.run/'ngspice.log'):raise ValueError('Changed source capture')
    chosen=[onset['trials'][0],onset['firstMaterialFrozenChange'],onset['firstExcursionTrial'],onset['trials'][-1]]
    ids={r['systemId'] for r in chosen if r};text=selected_log(a.run/'ngspice.log',ids);systems,incomplete=parse(text);caps=caps_parse(text)
    if incomplete or {s['id'] for s in systems}!=ids:raise ValueError('Missing selected systems')
    rows=[sensitivity(s,caps[s['id']]) for s in systems]
    result={'completed':True,'qualified':False,'scope':__doc__,'sourceReportSha256':sha(a.run/'report.json'),'logSha256':sha(a.run/'ngspice.log'),'onsetSha256':sha(a.onset),'systems':rows,'sources':{name:sha(Path(__file__).parent/name) for name in ['history_sensitivity_review.py','capacitor_stamp_review.py','linear_system_review.py','linear_precision_review.py']},'boundary':'Linearized frozen equations with exact local capacitor additions. Independent half-ULP perturbations of stored q1/i1 are hypothetical, not measured errors or a bound on accumulated integration error. No transient rerun, causal attribution, device qualification or convergence claim.'}
    a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps([{k:r[k] for k in ('systemId','independentHalfUlpHistoryBoundV')} for r in rows]))
if __name__=='__main__':main()
