#!/usr/bin/env python3
"""Replay captured inductor integration and stamps without changing stored histories."""
import argparse,hashlib,json,lzma,re
from fractions import Fraction as F
from pathlib import Path
from linear_system_review import parse
from linear_precision_review import solve
from capacitor_stamp_review import parse as cap_parse, corrections

def chains(log):
 pending=[];result={}
 for line in log.splitlines():
  if line.startswith('IND_CHAIN '):
   fields=dict(re.findall(r'(\w+)=([^\s]+)',line))
   pending.append({k:v if k=='name' else int(v) if k in ('mode','order','state','p','n','branch') else F(float.fromhex(v)) for k,v in fields.items()})
  elif line.startswith('LINEAR_AUDIT begin ') and pending:
   f=dict(re.findall(r'(\w+)=([^\s]+)',line))
   if any(r['time']!=F(float.fromhex(f['time'])) or r['delta']!=F(float.fromhex(f['delta'])) for r in pending):raise ValueError('Unmatched inductor load')
   if len({r['name'] for r in pending})!=len(pending):raise ValueError('Duplicate inductor load')
   result[int(f['id'])]=pending;pending=[]
 if pending or not result:raise ValueError('Incomplete inductor chain')
 return result

def corrected_system(system, records):
 branches={r['branch'] for r in records}
 if any(system['a'].get((i,j),F(0)) for i in branches for j in branches if i!=j):raise ValueError('Mutual inductance is outside this replay')
 fixed=dict(system,a=dict(system['a']),b=dict(system['b']));rows=[]
 for r in records:
  if r['order'] not in (1,2):raise ValueError('Only trapezoidal order 1/2')
  branch=r['branch'];exact_req=r['ag0']*r['L']/r['m']
  history=r['ag1']*r['q1'] if r['order']==1 else -r['ag1']*r['v1']-r['ag0']*r['q1']
  if system['a'][branch,branch]!=F(float(r['diag']-r['req'])) or system['b'][branch]!=F(float(r['rhs']+r['veq'])):raise ValueError('Other branch stamp or mismatch')
  fixed['a'][branch,branch]=r['diag']-exact_req;fixed['b'][branch]=r['rhs']+history
  voltage=r['ag0']*r['q0']+history
  rows.append({'name':r['name'],'branch':branch,'acceptedFlux':float(r['q1']),'trialFlux':float(r['q0']),
               'historyCurrent':float(r['q1']*r['m']/r['L']), 'recordedCurrentBeforeLoad':float(r['current']),
               'fluxProductError':float(r['q0']-r['L']/r['m']*r['current']),
               'integratedVoltageError':float(r['v0']-voltage),'reqError':float(r['req']-exact_req),
               'historySourceError':float(r['veq']-history)})
 return fixed,rows

def assess(log):
 systems,incomplete=parse(log);loads=chains(log);system=next(s for s in reversed(systems) if s['id'] in loads)
 fixed,rows=corrected_system(system,loads[system['id']]);original=solve(system,80);corrected=solve(fixed,80);confirm=solve(fixed,160)
 group=cap_parse(log)[system['id']];ca,cb,_=corrections(group)
 capfixed=dict(system,a=dict(system['a']),b=dict(system['b']))
 for k,v in ca.items():capfixed['a'][k]=capfixed['a'].get(k,F(0))+v
 for k,v in cb.items():capfixed['b'][k]+=v
 capsolution=solve(capfixed,80)
 paired=dict(system,a=dict(system['a']),b=dict(system['b']))
 for c in group['capacitors']:
  before,after=c['before'],c['after']
  if not before['p'] or not before['n']:continue
  history=F(before['m']*before['ceq'])
  for key,node,sign in [('bp',before['p'],-1),('bn',before['n'],1)]:
   paired['b'][node]+=sign*history-(F(after[key])-F(before[key]))
 pairedsolution=solve(paired,80);pairedconfirm=solve(paired,160)
 island=[i for i,n in system['names'].items() if n.startswith(('n_cable_','l1_'))]
 residual_columns={system['names'][j]:float(sum((system['a'].get((i,j),F(0)) for i in island),F(0))) for j in system['b']}
 balance={'nodes':[system['names'][i] for i in island], 'originalRhsSum':float(sum((system['b'][i] for i in island),F(0))),
          'pairedRhsSum':float(sum((paired['b'][i] for i in island),F(0))), 'nonzeroColumnSums':{k:v for k,v in residual_columns.items() if v},
          'pairedPrecisionAgreement':float(max(abs(pairedsolution[i]-pairedconfirm[i]) for i in pairedsolution))}
 for row in rows:
  i=row['branch'];row.update(capacitorCorrectedCurrent=float(capsolution[i]),pairedCorrectedCurrent=float(pairedsolution[i]))
  i=row['branch'];row.update(recordedSolvedCurrent=float(system['x'][i]),replayedCurrent=float(original[i]),correctedCurrent=float(corrected[i]))
 return {'qualified':False,'systemId':system['id'],'metadata':system['metadata'],'inductors':rows,'cableBalance':balance,
         'maximumSolveReplayDifference':float(max(abs(original[i]-system['x'][i]) for i in original)),
         'maximumCorrection':float(max(abs(corrected[i]-original[i]) for i in original)),
         'precisionAgreement':float(max(abs(corrected[i]-confirm[i]) for i in corrected)),
         'incompleteSystemsExcluded':incomplete,
         'boundary':'Frozen binary64 stored histories and other device stamps; Independent inductor, full-capacitor and paired-RHS corrections are compared separately. No mutual inductance is assumed. Does not establish live convergence.'}

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('log',type=Path);p.add_argument('--out',type=Path,required=True);a=p.parse_args();data=a.log.read_bytes();r=assess((lzma.decompress(data) if a.log.suffix=='.xz' else data).decode());r['logSha256']=hashlib.sha256(data).hexdigest();a.out.write_text(json.dumps(r,indent=2)+'\n')
