import sys,os,json,subprocess,time
from pathlib import Path
root=Path('/Users/ddanila/fun/dac-emulation');sys.path.insert(0,str(root/'verification/robotron-keyboard/analog'))
from ngspice_runtime import identify
from compressed_output import capture
from ttl7406_probe import sha
base=root/'build/keyboard-controller-analog/live-state-smoke'
runtime,env=identify('/private/tmp/k7658-rollback-runtime','/private/tmp/k7658-live-state-v3/spinit')
for k in list(env):
 if k.startswith('ROBOTRON_'):del env[k]
previous=json.loads((root/'build/keyboard-controller-analog/postreset-bridge/run.json').read_text())
env.update(previous['environment']);env.pop('ROBOTRON_ROLLBACK_AUDIT')
for mode in ('observe','check','corrupt'):
 d=base/mode;env['ROBOTRON_LIVE_STATE']=mode;start=time.monotonic()
 with capture(d,['waveform.raw','ngspice.log']) as storage:
  with (d/'ngspice.log').open('w') as log:
   p=subprocess.run([runtime['executable']['path'],'-n','-b','io.cir'],cwd=d,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=600)
 receipt={'runtime':runtime,'environment':{k:v for k,v in env.items() if k.startswith('ROBOTRON_')},'exitCode':p.returncode,'elapsedSeconds':time.monotonic()-start,'storage':storage,'inputs':{n:sha(d/n) for n in ('io.cir','io.vvp','s600.hex')},'builder':sha(root/'verification/robotron-keyboard/analog/build_live_state_audit.py'),'runner':sha(Path(__file__))}
 (d/'run.json').write_text(json.dumps(receipt,indent=2)+'\n');print(mode,p.returncode,receipt['elapsedSeconds'],flush=True)
