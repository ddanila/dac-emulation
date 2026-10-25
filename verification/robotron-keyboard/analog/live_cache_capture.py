#!/usr/bin/env python3
"""Capture an exact-cache control with compressed waveform and audit output."""
from pathlib import Path
import json,subprocess,time,shutil
from ngspice_runtime import identify,verify
from eval_cache_benchmark import external_dependencies,verify_dependencies
from compressed_output import capture
from audit_log import scan
from ttl7406_probe import sha
import argparse

def run(control,out,timeout):
 prior=json.loads((control/'run.json').read_text())
 if prior['exitCode']!=0 or prior['timedOut'] or prior.get('error') or prior['solverDiagnostic']:
  raise ValueError('Need a complete uncached control')
 runtime,env=identify(prior['runtime']['executable']['path'],prior['runtime']['spinit']['path'])
 if runtime!=prior['runtime']:raise ValueError('Changed runtime')
 if prior['environment']['ROBOTRON_EVAL_CACHE']!='off':raise ValueError('Need uncached control')
 for key in list(env):
  if key.startswith('ROBOTRON_'):del env[key]
 env.update(prior['environment']);env['ROBOTRON_EVAL_CACHE']='exact'
 deps=external_dependencies(control,{'deck':'io.cir','inputs':['io.vvp','s600.hex']})
 if deps!=prior['externalDependencies']:raise ValueError('Changed dependencies')
 for name,digest in dict(prior['inputs'],**{'io.cir':prior['deckSha256']}).items():
  if sha(control/name)!=digest:raise ValueError('Changed control input')
 out.mkdir(parents=True,exist_ok=False)
 for name in ('io.cir','io.vvp','s600.hex','bridge.json'):shutil.copyfile(control/name,out/name)
 shutil.copyfile(__file__,out/'capture-generator.py')
 r={'runtime':runtime,'externalDependencies':deps,'environment':{k:v for k,v in env.items() if k.startswith('ROBOTRON_')},
    'inputs':prior['inputs'],'deckSha256':prior['deckSha256'],'controlRunSha256':sha(control/'run.json'),
    'generatorSha256':sha(Path(__file__)),'exitCode':None,'timedOut':False,'qualified':False}
 start=time.monotonic()
 try:
  with capture(out,['waveform.raw','ngspice.log']) as storage:
   with (out/'ngspice.log').open('w') as log:
    process=subprocess.run([runtime['executable']['path'],'-n','-b','io.cir'],cwd=out,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=timeout)
   r['exitCode']=process.returncode
   if process.returncode:raise ValueError('Cache-control producer failed')
  r['storage']=storage;verify(runtime);verify_dependencies(deps)
  summary=scan(out/'ngspice.log');r['solverDiagnostic']=summary['diagnostic']
  if summary['diagnostic'] or summary['sorry']:raise ValueError('Solver/HDL diagnostic')
 except Exception as exc:
  r['error']=str(exc);r['timedOut']=isinstance(exc,subprocess.TimeoutExpired);raise
 finally:
  r['elapsedSeconds']=time.monotonic()-start
  (out/'run.json').write_text(json.dumps(r,indent=2)+'\n');print(out/'run.json',flush=True)

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--control',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
 p.add_argument('--timeout',type=float,default=10800);args=p.parse_args()
 run(args.control,args.out,args.timeout)
