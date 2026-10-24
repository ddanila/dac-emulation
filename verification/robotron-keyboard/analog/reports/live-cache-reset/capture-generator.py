from pathlib import Path
import json,subprocess,sys,time,shutil
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'verification/robotron-keyboard/analog'))
from ngspice_runtime import identify,verify
from eval_cache_benchmark import external_dependencies,verify_dependencies
from compressed_output import capture
from filter_truncation_log import diagnostic
from ttl7406_probe import sha
control=Path(sys.argv[1]);out=Path(sys.argv[2]);prior=json.loads((control/'run.json').read_text())
assert prior['exitCode']==0 and not prior['timedOut'] and not prior.get('error') and not prior['solverDiagnostic']
runtime,env=identify(prior['runtime']['executable']['path'],prior['runtime']['spinit']['path'])
assert runtime==prior['runtime']
assert prior['environment']['ROBOTRON_EVAL_CACHE']=='off'
for key in list(env):
 if key.startswith('ROBOTRON_'):del env[key]
env.update(prior['environment']);env['ROBOTRON_EVAL_CACHE']='exact'
deps=external_dependencies(control,{'deck':'io.cir','inputs':['io.vvp','s600.hex']});assert deps==prior['externalDependencies']
for name,digest in dict(prior['inputs'],**{'io.cir':prior['deckSha256']}).items():assert sha(control/name)==digest
out.mkdir(parents=True,exist_ok=False)
for name in ('io.cir','io.vvp','s600.hex','bridge.json'):shutil.copyfile(control/name,out/name)
shutil.copyfile(__file__,out/'capture-generator.py')
r={'runtime':runtime,'externalDependencies':deps,'environment':{k:v for k,v in env.items() if k.startswith('ROBOTRON_')},
   'inputs':prior['inputs'],'deckSha256':prior['deckSha256'],'controlRunSha256':sha(control/'run.json'),
   'generatorSha256':sha(Path(__file__)),'exitCode':None,'timedOut':False,'qualified':False}
start=time.monotonic()
try:
 with capture(out,['waveform.raw']) as storage:
  with (out/'ngspice.log').open('w') as log:
   process=subprocess.run([runtime['executable']['path'],'-n','-b','io.cir'],cwd=out,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=3600)
  r['exitCode']=process.returncode
  if process.returncode:raise ValueError('Cache-control producer failed')
 r['storage']=storage;verify(runtime);verify_dependencies(deps)
 log=(out/'ngspice.log').read_text();r['solverDiagnostic']=diagnostic(log)
 if r['solverDiagnostic'] or 'SORRY:' in log:raise ValueError('Solver/HDL diagnostic')
except Exception as exc:
 r['error']=str(exc);r['timedOut']=isinstance(exc,subprocess.TimeoutExpired);raise
finally:
 r['elapsedSeconds']=time.monotonic()-start
 (out/'run.json').write_text(json.dumps(r,indent=2)+'\n');print(out/'run.json',flush=True)
