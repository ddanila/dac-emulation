#!/usr/bin/env python3
"""Compare opt-in evaluator caching using an identical prepared startup deck."""
import argparse,json,os,shutil,subprocess,time,statistics,math,re
from pathlib import Path
from ttl7406_probe import sha
from failure_evidence import solver_diagnostic
from ngspice_runtime import identify,verify,fingerprint
HERE=Path(__file__).resolve().parent

def capture_scope(deck):
 # Prepared decks use numeric SI seconds. Reject unsupported syntax explicitly.
 lines=[line.split() for line in deck.splitlines() if line.strip().lower().startswith(('.tran ','tran '))]
 if len(lines)!=1:raise ValueError('Expected one transient analysis')
 tokens=lines[0][1:];uic=tokens[-1].lower()=='uic'
 if uic:tokens=tokens[:-1]
 if lines[0][0].lower()=='tran' and len(tokens)==2:tokens.append('0')
 if len(tokens)!=3:raise ValueError('Expected numeric transient step stop start')
 def seconds(token):
  match=re.fullmatch(r'([0-9.eE+\-]+)([num]?)',token)
  if not match:raise ValueError('Unsupported transient time: '+token)
  return float(match[1])*{'':1,'n':1e-9,'u':1e-6,'m':1e-3}[match[2]]
 step,stop,start=map(seconds,tokens)
 if not all(map(math.isfinite,(step,stop,start))) or not (step>0 and 0<=start<stop):raise ValueError('Invalid transient window')
 result={'startSeconds':start,'stopSeconds':stop,'stepSeconds':step}
 if uic:result['useInitialConditions']=True
 return result

def valid_start(first,scope):
 tolerance=max(1e-15,scope['stepSeconds']*1e-6)
 return math.isfinite(first) and scope['startSeconds']-tolerance<=first<=scope['startSeconds']+(scope['stepSeconds'] if scope.get('useInitialConditions') else tolerance)

def fixture(root):
 path=root/'fixture.json'
 spec=json.loads(path.read_text()) if path.exists() else {'deck':'boot.cir','inputs':['boot.cir','boot.vvp','s600.hex','ls_nand_nominal.cir'],'traces':['trace.txt','supply-trace.txt']}
 for field in ('inputs','traces'):
  if not spec[field] or len(set(spec[field]))!=len(spec[field]):raise ValueError('Invalid fixture files')
  if any(Path(n).name!=n or n in ('.','..') for n in spec[field]):raise ValueError('Fixture files must be local basenames')
 if spec['deck'] not in spec['inputs'] or set(spec['inputs']) & set(spec['traces']):raise ValueError('Invalid fixture deck or traces')
 return spec

def validate_extent(extent,scope):
 if not isinstance(extent['samples'],int) or isinstance(extent['samples'],bool) or extent['samples']<2:raise ValueError('Incomplete retained capture')
 if not all(math.isfinite(extent[k]) for k in ('firstSeconds','lastSeconds','minimumValue','maximumValue')):raise ValueError('Nonfinite retained capture')
 if extent['minimumValue']>extent['maximumValue']:raise ValueError('Invalid retained voltage range')
 if not valid_start(extent['firstSeconds'],scope) or abs(extent['lastSeconds']-scope['stopSeconds'])>max(1e-15,scope['stepSeconds']*1e-6):raise ValueError('Incomplete retained capture')

def trace_extent(path,scope):
 count=0;first=last=None;low=high=None
 with path.open() as stream:
  columns=len(next(stream,'').split())
  if columns<2:raise ValueError('Missing trace vectors')
  for line in stream:
   values=list(map(float,line.split()))
   if len(values)!=columns or not all(map(math.isfinite,values)):raise ValueError('Invalid trace row')
   t=values[0]
   if last is not None and t<=last:raise ValueError('Non-increasing trace time')
   if first is None:first=t
   last=t;count+=1
   low=min(values[1:]) if low is None else min(low,*values[1:])
   high=max(values[1:]) if high is None else max(high,*values[1:])
 tolerance=max(1e-15,scope['stepSeconds']*1e-6)
 if count<2 or not valid_start(first,scope) or abs(last-scope['stopSeconds'])>tolerance:raise ValueError('Incomplete trace window')
 return {'samples':count,'firstSeconds':first,'lastSeconds':last,'minimumValue':low,'maximumValue':high}

def external_dependencies(prepared,spec):
 paths=set(re.findall(r'"(/[^"\n]+)"',(prepared/spec['deck']).read_text()))
 for name in spec['inputs']:
  if name.endswith('.vvp'):
   paths.update(re.findall(r'^:vpi_module "([^"\n]+)";', (prepared/name).read_text(),re.M))
 if any(not Path(p).is_absolute() for p in paths):raise ValueError('VPI dependencies require explicit absolute paths')
 return [fingerprint(p) for p in sorted(paths)]

def verify_dependencies(receipts):
 for item in receipts:
  if fingerprint(item['path'])!=item:raise ValueError('External co-simulation dependency changed: '+item['path'])

def assess(root):
 spec=fixture(root)
 runs=[json.loads((root/n/'run.json').read_text()) for n in ('off','exact','off-repeat','exact-repeat')]
 for n,r in zip(('off','exact','off-repeat','exact-repeat'),runs):
  if r['mode']!=n or not math.isfinite(r['elapsedSeconds']) or r['elapsedSeconds']<=0:raise ValueError('Invalid run identity or timing: '+n)
  if set(r['sha256'])!=set(spec['traces']):raise ValueError('Incomplete waveform hashes: '+n)
  if r.get('failure') or r['exitCode'] or solver_diagnostic((root/n/'ngspice.log').read_text()):raise ValueError('Failed benchmark: '+n)
 scope=json.loads((root/'scope.json').read_text()) if (root/'scope.json').exists() else None
 if scope:
  if capture_scope((root/spec['deck']).read_text())!=scope:raise ValueError('Stale capture scope')
  for n,r in zip(('off','exact','off-repeat','exact-repeat'),runs):
   for name in spec['traces']:
    extent=r['capture'][name]
    validate_extent(extent,scope)
    if (root/n/name).exists() and trace_extent(root/n/name,scope)!=extent:raise ValueError('Changed capture extent')
 identical=all(r['sha256']==runs[0]['sha256'] for r in runs)
 if not identical:raise ValueError('Cache changed recorded waveforms')
 off=statistics.mean(r['elapsedSeconds'] for r in runs if r['mode'].startswith('off'));on=statistics.mean(r['elapsedSeconds'] for r in runs if r['mode'].startswith('exact'))
 return {'completed':True,'qualified':False,'waveformsByteIdentical':identical,'meanDisabledSeconds':off,'meanEnabledSeconds':on,'elapsedReductionFraction':1-on/off,'scope':({'capture':scope,'limitation':'Prepared-deck equivalence only; no physical or full-service qualification. Timing is local, not a CI threshold.'} if scope else '500 us startup only, below rated supply; no full-board or long-run performance qualification. Timing is a local measurement, not a CI threshold.')}

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--prepared',type=Path);p.add_argument('--out',type=Path,required=True);p.add_argument('--ngspice');p.add_argument('--spinit');p.add_argument('--verify',action='store_true');p.add_argument('--timeout',type=float,default=300);a=p.parse_args()
 if a.verify:
  for n,h in json.loads((a.out/'manifest.json').read_text()).items():
   if sha(a.out/n)!=h:raise ValueError('Changed benchmark evidence: '+n)
  if assess(a.out)!=json.loads((a.out/'assessment.json').read_text()):raise ValueError('Stale benchmark assessment')
  print('Scoped cache benchmark verified');return
 if not all((a.prepared,a.ngspice,a.spinit)):p.error('Prepared startup, runtime and spinit required')
 spec=fixture(a.prepared)
 runtime,env=identify(a.ngspice,Path(a.spinit)/'spinit')
 dependencies=external_dependencies(a.prepared,spec)
 scope=capture_scope((a.prepared/spec['deck']).read_text())
 a.out.mkdir(parents=True,exist_ok=False)
 shutil.copyfile(a.prepared/spec['deck'],a.out/spec['deck'])
 (a.out/'fixture.json').write_text(json.dumps(spec,indent=2)+'\n')
 (a.out/'scope.json').write_text(json.dumps(scope,indent=2)+'\n')
 inputs={n:sha(a.prepared/n) for n in spec['inputs']}
 (a.out/'runtime.json').write_text(json.dumps({'runtime':runtime,'externalDependencies':dependencies,'experimentalEnvironment':{k:v for k,v in env.items() if k.startswith('ROBOTRON_') and k!='ROBOTRON_EVAL_CACHE'},'patchSha256':sha(HERE/'engine-patches/eval-cache.patch'),'inputSha256':inputs},indent=2)+'\n')
 for mode in ('off','exact','off-repeat','exact-repeat'):
  folder=a.out/mode;folder.mkdir()
  for n in spec['inputs']:shutil.copyfile(a.prepared/n,folder/n)
  if any(sha(folder/n)!=h for n,h in inputs.items()):raise ValueError('Prepared input changed between runs')
  verify_dependencies(dependencies)
  start=time.monotonic();failure=None
  with (folder/'ngspice.log').open('w') as log:
   try:
    process=subprocess.run([a.ngspice,'-n','-b',spec['deck']],cwd=folder,env=dict(env,ROBOTRON_EVAL_CACHE=mode.split('-')[0]),stdout=log,stderr=subprocess.STDOUT,timeout=a.timeout)
    code=process.returncode
   except subprocess.TimeoutExpired:
    code=-1;failure='Simulation timed out'
  result={'mode':mode,'elapsedSeconds':time.monotonic()-start,'exitCode':code,'sha256':{},'capture':{}}
  try:
   for n in spec['traces']:
    if (folder/n).exists():result['sha256'][n]=sha(folder/n)
   if failure or code or solver_diagnostic((folder/'ngspice.log').read_text()):raise ValueError(failure or 'Solver failure')
   result['capture']={n:trace_extent(folder/n,scope) for n in spec['traces']}
   verify(runtime)
   verify_dependencies(dependencies)
  except (ValueError,OSError) as error:
   result['failure']=str(error)
  (folder/'run.json').write_text(json.dumps(result,indent=2)+'\n')
  if 'failure' in result:raise ValueError('Failed benchmark '+mode+': '+result['failure'])
 (a.out/'assessment.json').write_text(json.dumps(assess(a.out),indent=2)+'\n')
 (a.out/'manifest.json').write_text(json.dumps({str(f.relative_to(a.out)):sha(f) for f in sorted(a.out.rglob('*')) if f.is_file()},indent=2)+'\n')
if __name__=='__main__':main()
