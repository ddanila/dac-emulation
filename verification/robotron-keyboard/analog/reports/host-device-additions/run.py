#!/usr/bin/env python3
"""Matched nonlinear-stamp experiment; unchanged circuit and acceptance budgets."""
import argparse,json,os,subprocess,sys
from pathlib import Path
A=Path(__file__).resolve().parents[2];sys.path.insert(0,str(A))
from analog_driver_replay import sha
from accepted_capture_review import budget_stop
p=argparse.ArgumentParser();p.add_argument('source',type=Path);p.add_argument('--runtime',type=Path,required=True);p.add_argument('--provenance',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--mode',choices=('off','exact'),required=True);p.add_argument('--step-divisor',type=int,choices=(1,2,4),default=1);a=p.parse_args()
provenance=json.loads(a.provenance.read_text())
if provenance['deviceHeaderSha256']!=sha(A/'engine-patches/device_additions.h') or provenance['executableSha256']!=sha(a.runtime):raise ValueError('Changed runtime')
env={k:v for k,v in os.environ.items() if not k.startswith('ROBOTRON_')}
env.update(ROBOTRON_CAP_ASSEMBLY='exact',ROBOTRON_POSTCAP_ASSEMBLY='exact',ROBOTRON_DEVICE_ASSEMBLY=a.mode,ROBOTRON_ACCEPTED_LIMIT='200',ROBOTRON_ACCEPTED_AFTER='.0010980122484353')
command=[sys.executable,str(A/'reports/host-represented-time/run.py'),str(a.source),'--time-step','represented','--integration-arithmetic','256','--mode','256','--step-divisor',str(a.step_divisor),'--runtime',str(a.runtime),'--build-provenance',str(a.provenance),'--out',str(a.out)]
subprocess.run(command,env=env,check=True)
report=json.loads((a.out/'report.json').read_text());parent=json.loads((a.source/'report.json').read_text())
log=(a.out/'ngspice.log').read_text();notices=[l for l in log.splitlines() if l.startswith('ACCEPTED_BUDGET ')]
if log.splitlines().count('DEVICE_ASSEMBLY mode='+str(int(a.mode=='exact')))!=1:raise ValueError('Missing mode witness')
identical={name:sha(a.out/name)==parent['artifacts'][name] for name in ('io.cir','trace.txt','host-trace.txt','driver-trace.txt','boundary-trace.txt')}
endpoint=budget_stop(notices,(a.out/'io.cir').read_text(),200,.0010980122484353,report['stopSeconds']) if any('stopped' in l for l in notices) else None
result={'qualified':False,'mode':a.mode,'command':command,'environment':{k:v for k,v in env.items() if k.startswith('ROBOTRON_')},'reportSha256':sha(a.out/'report.json'),'runtimeProvenanceSha256':sha(a.provenance),'runnerSha256':sha(__file__),'completed':report['completed'],'solverDiagnostic':report['solverDiagnostic'],'endpoint':endpoint,'operationallyTruncated':bool(endpoint),'identicalArtifacts':identical,'disabledControlPassed':a.mode=='off' and all(identical.values()) and report['solverDiagnostic']==parent['solverDiagnostic'],'scope':'Exact accumulation of evaluated binary64 BJT and diode matrix/RHS contributions, added to existing capacitor/resistor/switch corrections. Nonlinear equations, stored history, circuit parameters and acceptance budgets unchanged. Analog-only replay does not qualify the coupled board.'}
(a.out/'device-control.json').write_text(json.dumps(result,indent=2)+'\n')
if a.mode=='off' and not result['disabledControlPassed']:raise ValueError('Disabled control changed')
print(a.out/'device-control.json')
