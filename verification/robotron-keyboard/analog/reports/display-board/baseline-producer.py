import json,sys,shutil,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];HERE=ROOT/'verification/robotron-keyboard/analog';sys.path.insert(0,str(HERE))
from postreset_refinement_capture import validate_control
from eval_cache_benchmark import external_dependencies,verify_dependencies
from bounded_log_process import run as producer
from compressed_output import capture
from ngspice_runtime import verify
from ttl7406_probe import sha
from audit_log import complete
b=ROOT/'build/keyboard-controller-analog';fixture=HERE/'reports/instance-queue-state/off'
coarse=b/'postreset-startup-combined';models=Path('/private/tmp/k7658-startup-fixes-v1')
control,inputs,runtime,base_env,_=validate_control(b/'postreset-newton-retry/off',coarse,models,Path('/private/tmp/k7658-selectable-retry-runtime'))
bridge=Path('/private/tmp/k7658-private-sync-bridge');icarus=Path('/private/tmp/k7658-icarus-sync-observer-v4')
for folder in (bridge,icarus):
 for name,digest in json.loads((folder/'build.json').read_text())['outputs'].items():assert sha(folder/name)==digest
old_shim=str(b/'bridge/ivlng.so');old_lib='/private/tmp/robotron-icarus-src/vvp/libvvp.so'
deck=(fixture/'io.cir').read_text();r=json.loads((fixture/'run.json').read_text())
assert sha(fixture/'io.cir')==r['inputs']['io.cir']
assert deck.count(old_shim)==deck.count(old_lib)==1
assert '.tran 25n 20000n' in deck and '1000n 0 1001n 5' in deck
root=b/'private-sync-board-controls';root.mkdir(exist_ok=False)
for mode in ('baseline','off','observe','corrupt'):
 out=root/mode;out.mkdir();text=deck if mode=='baseline' else deck.replace(old_shim,str(bridge/'ivlng.so')).replace(old_lib,str(icarus/'vvp/libvvp.so'))
 for name in ('io.vvp','s600.hex'):
  assert sha(fixture/name)==inputs[name];shutil.copyfile(fixture/name,out/name)
 (out/'io.cir').write_text(text)
 env=base_env.copy();env['ROBOTRON_PRIVATE_SYNC']='off' if mode=='baseline' else mode
 deps=external_dependencies(out,{'deck':'io.cir','inputs':['io.vvp','s600.hex']})
 record={'qualified':False,'completed':False,'mode':mode,'runtime':runtime,'environment':{k:v for k,v in env.items() if k.startswith('ROBOTRON_')},'externalDependencies':deps,'inputs':{f:sha(out/f) for f in ('io.cir','io.vvp','s600.hex')},'fixtureReceiptSha256':sha(fixture/'run.json'),'combinedControlReceiptSha256':sha(coarse/'run.json'),'bridgeBuildSha256':sha(bridge/'build.json'),'icarusBuildSha256':sha(icarus/'build.json'),'producerSha256':sha(Path(__file__)),'endSeconds':20e-6,'expectedExitCode':2 if mode=='corrupt' else 0}
 start=time.monotonic();(out/'run.json').write_text(json.dumps(record,indent=2)+'\n')
 try:
  with capture(out,['waveform.raw']) as storage:
   log=producer([runtime['executable']['path'],'-n','-b','io.cir'],out,env,out/'ngspice.log.xz',900,logical_limit=512*1024**2,compressed_limit=128*1024**2,min_free_bytes=512*1024**2)
  record.update(storage=storage,log=log,exitCode=log['exitCode'])
  verify(runtime);verify_dependencies(deps)
  assert all(sha(out/f)==h for f,h in record['inputs'].items())
  if log['exitCode']!=record['expectedExitCode']:raise ValueError('Unexpected simulator exit; a zero corrupt exit means the callback-mode fault was not exercised')
  if mode!='corrupt':record['summary']=complete(out/'ngspice.log')
  record['completed']=True
 except Exception as exc:record['error']=str(exc)
 record['elapsedSeconds']=time.monotonic()-start;(out/'run.json').write_text(json.dumps(record,indent=2)+'\n')
 print(mode,record['completed'],record.get('error',''),flush=True)
