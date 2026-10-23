#!/usr/bin/env python3
"""Distinguish output-switch Newton chatter from truncation rejection."""
import argparse,hashlib,json,lzma,re
from pathlib import Path
from truncation_arithmetic_review import review_record
from analog_driver_replay import recorded_trtol

def review(log):
 pending=[];trials=[]
 for line in log.splitlines():
  if line.startswith('SWITCH_AUDIT '):
   fields=dict(re.findall(r'(\w+)=([^\s]+)',line))
   pending.append({k:int(v) if k in ('mode','noncon') else float.fromhex(v) for k,v in fields.items()})
  elif line.startswith('SWITCH_SOLVER '):
   f=dict(re.findall(r'(\w+)=([^\s]+)',line));t=float.fromhex(f['time']);d=float.fromhex(f['delta'])
   if not pending or any(r['time']!=t or r['delta']!=d for r in pending):raise ValueError('Missing or mixed switch loads')
   trials.append({'time':t,'delta':d,'result':int(f['result']),'loads':len(pending),
                  'stateChanges':sum(r['old']!=r['current'] for r in pending),
                  'controlRange':[min(r['control'] for r in pending),max(r['control'] for r in pending)],
                  'thresholds':sorted(set(r['threshold'] for r in pending)),
                  'states':sorted(set(r['current'] for r in pending)),
                  'lastLoads':pending[-6:]})
   pending=[]
 if not trials or pending:raise ValueError('Incomplete switch capture')
 errors=[dict(re.findall(r'(\w+)=([^\s]+)',line)) for line in log.splitlines() if line.startswith('TRUNC_AUDIT error ')]
 instances=[dict(re.findall(r'(\w+)=([^\s]+)',line)) for line in log.splitlines() if line.startswith('TRUNC_AUDIT instance ')]
 late=None
 if errors:
  late={'lastEstimator':review_record(errors[-1],1e-15,recorded_trtol(log)), 'lastLimitingInstance':instances[-1]}
 return {'qualified':False,'lateTruncation':late,'trials':trials,'boundary':'Read-only switch and Newton status capture; not a physical driver model or a convergence correction.'}

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('log',type=Path);p.add_argument('--out',type=Path,required=True);a=p.parse_args();data=a.log.read_bytes();r=review((lzma.decompress(data) if a.log.suffix=='.xz' else data).decode());r['logSha256']=hashlib.sha256(data).hexdigest();a.out.write_text(json.dumps(r,indent=2)+'\n')
