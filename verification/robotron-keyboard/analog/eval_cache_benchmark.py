#!/usr/bin/env python3
"""Compare opt-in evaluator caching using an identical prepared startup deck."""
import argparse,json,os,shutil,subprocess,time,statistics
from pathlib import Path
from ttl7406_probe import sha
from failure_evidence import solver_diagnostic
HERE=Path(__file__).resolve().parent

def assess(root):
 runs=[json.loads((root/n/'run.json').read_text()) for n in ('off','exact','off-repeat','exact-repeat')]
 for n,r in zip(('off','exact','off-repeat','exact-repeat'),runs):
  if r['exitCode'] or solver_diagnostic((root/n/'ngspice.log').read_text()):raise ValueError('Failed benchmark: '+n)
 identical=all(r['sha256']==runs[0]['sha256'] for r in runs)
 if not identical:raise ValueError('Cache changed recorded waveforms')
 off=statistics.mean(r['elapsedSeconds'] for r in runs if r['mode'].startswith('off'));on=statistics.mean(r['elapsedSeconds'] for r in runs if r['mode'].startswith('exact'))
 return {'completed':True,'qualified':False,'waveformsByteIdentical':identical,'meanDisabledSeconds':off,'meanEnabledSeconds':on,'elapsedReductionFraction':1-on/off,'scope':'500 us startup only, below rated supply; no full-board or long-run performance qualification. Timing is a local measurement, not a CI threshold.'}

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--prepared',type=Path);p.add_argument('--out',type=Path,required=True);p.add_argument('--ngspice');p.add_argument('--spinit');p.add_argument('--verify',action='store_true');a=p.parse_args()
 if a.verify:
  for n,h in json.loads((a.out/'manifest.json').read_text()).items():
   if sha(a.out/n)!=h:raise ValueError('Changed benchmark evidence: '+n)
  if assess(a.out)!=json.loads((a.out/'assessment.json').read_text()):raise ValueError('Stale benchmark assessment')
  print('Scoped cache benchmark verified');return
 if not all((a.prepared,a.ngspice,a.spinit)):p.error('Prepared startup, runtime and spinit required')
 a.out.mkdir(parents=True,exist_ok=False)
 for mode in ('off','exact','off-repeat','exact-repeat'):
  folder=a.out/mode;folder.mkdir()
  for n in ('boot.cir','boot.vvp','s600.hex','ls_nand_nominal.cir'):shutil.copyfile(a.prepared/n,folder/n)
  start=time.monotonic()
  with (folder/'ngspice.log').open('w') as log:
   p=subprocess.run([a.ngspice,'-n','-b','boot.cir'],cwd=folder,env=dict(os.environ,SPICE_SCRIPTS=a.spinit,ROBOTRON_EVAL_CACHE=mode.split('-')[0]),stdout=log,stderr=subprocess.STDOUT,timeout=180)
  result={'mode':mode,'elapsedSeconds':time.monotonic()-start,'exitCode':p.returncode,'sha256':{n:sha(folder/n) for n in ('trace.txt','supply-trace.txt')}}
  (folder/'run.json').write_text(json.dumps(result,indent=2)+'\n')
 (a.out/'runtime.json').write_text(json.dumps({'executableSha256':sha(Path(a.ngspice)),'patchSha256':sha(HERE/'engine-patches/eval-cache.patch'),'inputSha256':{n:sha(a.prepared/n) for n in ('boot.cir','boot.vvp','s600.hex','ls_nand_nominal.cir')}},indent=2)+'\n')
 (a.out/'assessment.json').write_text(json.dumps(assess(a.out),indent=2)+'\n')
 (a.out/'manifest.json').write_text(json.dumps({str(f.relative_to(a.out)):sha(f) for f in sorted(a.out.rglob('*')) if f.is_file()},indent=2)+'\n')
if __name__=='__main__':main()
