#!/usr/bin/env python3
"""Replay opt-in exact capacitor-addition corrections through the MPFR solve."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ANALOG = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ANALOG))
from analog_driver_replay import sha

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('source',type=Path)
p.add_argument('--runtime',type=Path,required=True)
p.add_argument('--build-provenance',type=Path,required=True)
p.add_argument('--mode',choices=('off','exact'),required=True)
p.add_argument('--step-divisor',type=int,choices=(1,2),default=1)
p.add_argument('--out',type=Path,required=True)
a=p.parse_args()
provenance=json.loads(a.build_provenance.read_text())
for key,name in [('assemblyPatchSha256','ngspice-47-capacitor-assembly.patch'),('assemblyHeaderSha256','capacitor_assembly.h')]:
    if provenance.get(key)!=sha(ANALOG/'engine-patches'/name):raise ValueError('Assembly build differs: '+name)
parent=json.loads((a.source/'report.json').read_text())
runner=ANALOG/'reports/host-represented-time/run.py'
command=[sys.executable,str(runner),str(a.source),'--time-step','represented',
         '--integration-arithmetic','256','--mode','256','--step-divisor',str(a.step_divisor),
         '--runtime',str(a.runtime),'--build-provenance',str(a.build_provenance),'--out',str(a.out)]
subprocess.run(command,env=dict(os.environ,ROBOTRON_CAP_ASSEMBLY=a.mode),check=True)
log=(a.out/'ngspice.log').read_text()
if re.findall(r'^CAP_ASSEMBLY mode=(-?\d+)$',log,re.M)!=[str(int(a.mode=='exact'))]:
    raise ValueError('Effective assembly mode not confirmed')
result=json.loads((a.out/'report.json').read_text())
identical={name:sha(a.out/name)==digest for name,digest in parent['artifacts'].items()
           if name in ('io.cir','trace.txt','host-trace.txt','driver-trace.txt','boundary-trace.txt')}
receipt={'qualified':False,'mode':a.mode,'sourceReportSha256':sha(a.source/'report.json'),
         'reportSha256':sha(a.out/'report.json'),'command':command,'wrapperSha256':sha(__file__),
         'assemblyPatchSha256':provenance['assemblyPatchSha256'],
         'assemblyHeaderSha256':provenance['assemblyHeaderSha256'],
         'identicalArtifacts':identical,'diagnosticEqual':result['solverDiagnostic']==parent['solverDiagnostic'],
         'completed':result['completed'],
         'boundary':'Exact rational corrections replace constant-capacitor local additions in the MPFR linear system. Binary64 matrix storage, all other stamping and previously rounded histories remain unchanged. Experimental analog replay, not coupled-board or physical qualification.'}
receipt['disabledControlPassed']=a.mode=='off' and a.step_divisor==1 and len(identical)==5 and all(identical.values()) and receipt['diagnosticEqual']
(a.out/'assembly-control.json').write_text(json.dumps(receipt,indent=2)+'\n')
if a.mode=='off' and not receipt['disabledControlPassed']:raise ValueError('Disabled correction changed control')
print(a.out/'assembly-control.json')
