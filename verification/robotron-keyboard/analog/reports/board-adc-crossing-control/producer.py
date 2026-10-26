#!/usr/bin/env python3
"""Matched bounded board control; pre-reset screening, not board qualification."""
import json,sys,shutil,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'verification/robotron-keyboard/analog'))
from postreset_refinement_capture import validate_control, ORIGINAL_TRAN
from bounded_log_process import run as producer
from compressed_output import capture
from ngspice_runtime import verify
from eval_cache_benchmark import verify_dependencies
from ttl7406_probe import sha
from audit_log import complete
from raw_pair_review import compare_raw
from postreset_refinement_review import voltage_gate
b=ROOT/'build/keyboard-controller-analog'
source=b/'postreset-newton-retry/off';coarse=b/'postreset-startup-combined'
models=Path('/private/tmp/k7658-startup-fixes-v1')
control,inputs,runtime,base_env,deps=validate_control(source,coarse,models,Path('/private/tmp/k7658-selectable-retry-runtime'))
out=b/'board-adc-crossing-control';out.mkdir(exist_ok=False)
assert shutil.disk_usage(out).free>2*1024**3
original=(coarse/'io.cir').read_text();assert original.count(ORIGINAL_TRAN)==1
results={}
for mode in ('off','on'):
 for step in (25,12.5,6.25):
  name=f'{mode}-{step:g}';folder=out/name;folder.mkdir()
  for file in inputs:
   if file!='io.cir':shutil.copyfile(coarse/file,folder/file)
  (folder/'io.cir').write_text(original.replace(ORIGINAL_TRAN,f'\n.tran {step:g}n 20000n\n'))
  env=base_env.copy()
  if mode=='on':env['ROBOTRON_ADC_CROSSINGS']='1'
  receipt={'completed':False,'qualified':False,'stepNs':step,'endSeconds':20e-6,'adcCrossings':mode,'runtime':runtime,'environment':{k:v for k,v in env.items() if k.startswith('ROBOTRON_')},'inputs':{f:sha(folder/f) for f in inputs},'externalDependencies':deps,'coarseRunSha256':sha(coarse/'run.json'),'candidateBuildSha256':sha(models/'build.json'),'producerSha256':sha(Path(__file__))}
  start=time.monotonic()
  try:
   with capture(folder,['waveform.raw']) as storage:
    log=producer([runtime['executable']['path'],'-n','-b','io.cir'],folder,env,folder/'ngspice.log.xz',600,logical_limit=256*1024**2,compressed_limit=64*1024**2,min_free_bytes=512*1024**2)
   receipt.update(storage=storage,log=log)
   verify(runtime);verify_dependencies(deps)
   assert all(sha(folder/f)==h for f,h in receipt['inputs'].items())
   if log['exitCode']!=0:raise ValueError('Producer exit '+str(log['exitCode']))
   receipt['summary']=complete(folder/'ngspice.log')
   receipt['coverage']=compare_raw(folder/'waveform.raw',folder/'waveform.raw',[receipt['summary']['count']]*2,20e-6,exact=True)
   receipt['completed']=True
  except Exception as exc:receipt['error']=str(exc)
  receipt['elapsedSeconds']=time.monotonic()-start
  (folder/'run.json').write_text(json.dumps(receipt,indent=2)+'\n');results[name]=receipt
  print(name,receipt['completed'],receipt.get('error',''),flush=True)
assessment={'qualified':False,'scope':'Unchanged combined-fix board and external clock/reset, truncated to 20 us before reset release. Only ADC crossing option and transient step differ; no post-reset firmware or full-window convergence claim.','runs':{n:{'completed':r['completed'],'error':r.get('error'),'receiptSha256':sha(out/n/'run.json')} for n,r in results.items()},'comparisons':{}}
for mode in ('off','on'):
 names=[f'{mode}-{s:g}' for s in (25,12.5,6.25)]
 if all(results[n]['completed'] for n in names):
  pairs=[compare_raw(out/names[i]/'waveform.raw',out/names[i+1]/'waveform.raw',[results[names[j]]['summary']['count'] for j in (i,i+1)],20e-6) for i in range(2)]
  assessment['comparisons'][mode]={'pairs':pairs,'gate':voltage_gate(*pairs)}
(out/'assessment.json').write_text(json.dumps(assessment,indent=2)+'\n')
print(out/'assessment.json',flush=True)
