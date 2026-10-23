#!/usr/bin/env python3
"""Separate capacitor assembly error from the first live timestep rejection."""
import argparse,json,lzma,hashlib
from pathlib import Path
from fractions import Fraction as F
from capacitor_stamp_review import parse as cap_parse,corrections
from linear_system_review import parse
from linear_precision_review import solve

def assess(log, terminal=False):
 systems,incomplete=parse(log);caps=cap_parse(log)
 # Select first order-one trial after the accepted clock-driven transition.
 candidates=[s for s in systems if float.fromhex(s['metadata']['time'])==.001005012816]
 if not candidates:raise ValueError('Missing original rejected trial')
 s=systems[-1] if terminal else candidates[-1];group=caps[s['id']];a,b,observations=corrections(group)
 corrected=dict(s,a=dict(s['a']),b=dict(s['b']))
 for key,value in a.items():corrected['a'][key]=corrected['a'].get(key,F(0))+value
 for key,value in b.items():corrected['b'][key]+=value
 original=solve(s,80);fixed=solve(corrected,80);confirm=solve(corrected,160)
 cap=next(c for c in group['capacitors'] if c['before']['name']=='cbus_a8_16')['before'];node=cap['p']
 change=max(abs(fixed[i]-original[i]) for i in original)
 return {'qualified':False,'systemId':s['id'],'time':s['metadata']['time'],'cap':cap,
         'recordedD6':float(s['x'][node]),'highPrecisionD6':float(original[node]),'correctedAssemblyD6':float(fixed[node]),
         'maximumAssemblySolutionChange':float(change),'correctedPrecisionAgreement':float(max(abs(fixed[i]-confirm[i]) for i in fixed)),
         'capacitorCorrections':observations,'incompleteSystemsExcluded':incomplete,
         'boundary':'Frozen constant-capacitor assembly correction; binary64 histories, other devices and nonlinear operating point unchanged. Does not qualify a live trajectory.'}

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('log',type=Path);p.add_argument('--terminal',action='store_true');p.add_argument('--out',type=Path,required=True);a=p.parse_args();data=a.log.read_bytes();log=(lzma.decompress(data) if a.log.suffix=='.xz' else data).decode();r=assess(log,a.terminal);r['logSha256']=hashlib.sha256(data).hexdigest();a.out.write_text(json.dumps(r,indent=2)+'\n')
