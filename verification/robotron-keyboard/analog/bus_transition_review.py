#!/usr/bin/env python3
"""Retain bounded transition evidence and distinguish completion from solver exit."""
import argparse,collections,json,math,re,shutil
from pathlib import Path
from ttl7406_probe import sha
from failure_evidence import solver_diagnostic
HERE=Path(__file__).resolve().parent
GROUPS={'tolerances':'bus-transition-screen','isolation':'bus-feedback-isolation','switch-controls':'bus-switch-controls','refinement':'bus-switch-refinement','second-transition':'bus-second-transition'}

def extent(path):
 tail=collections.deque(maxlen=32);count=0;first=None;last=None
 with path.open() as stream:
  header=next(stream).split()
  for line in stream:
   row=list(map(float,line.split()))
   if len(row)!=len(header) or not all(map(math.isfinite,row)) or (last is not None and row[0]<last):raise ValueError('Invalid diagnostic trace')
   first=row[0] if first is None else first;last=row[0];count+=1;tail.append(row)
 return {'sha256':sha(path),'columns':header,'rows':count,'firstSeconds':first,'lastSeconds':last,'tail':list(tail)}

def stop_time(deck):
 value=re.search(r'^\.tran\s+\S+\s+(\S+)',deck,re.M)[1]
 m=re.fullmatch(r'([\d.eE+-]+)([num]?)',value)
 if not m:raise ValueError('Unsupported stop time')
 return float(m[1])*{'':1,'n':1e-9,'u':1e-6,'m':1e-3}[m[2]]

def assess(root):
 cases={}
 for receipt in sorted(root.glob('*/*/run.json')):
  folder=receipt.parent;r=json.loads(receipt.read_text());diagnostic=solver_diagnostic((folder/'ngspice.log').read_text());trace=json.loads((folder/'trace-summary.json').read_text()) if (folder/'trace-summary.json').exists() else None
  stop=stop_time((folder/'io.cir').read_text());complete=r.get('exitCode')==0 and not r.get('timedOut',False) and not diagnostic and trace is not None and abs(trace['lastSeconds']-stop)<1e-12
  cases[str(folder.relative_to(root))]={'completed':complete,'diagnostic':diagnostic,'timedOut':r.get('timedOut',False),'lastSeconds':trace['lastSeconds'] if trace else None,'requestedStopSeconds':stop}
 expected={'tolerances/nominal':True,'tolerances/relative':False,'tolerances/voltage':True,'tolerances/current':True,'isolation/replay-tight':False,'isolation/no-bus':False,'switch-controls/after-replay-tight':True,'switch-controls/after-tight':False,'second-transition/replay-tight':True}
 for name,completed in expected.items():
  if cases[name]['completed']!=completed:raise ValueError('Transition findings need review: '+name)
 before=json.loads((root/'switch-before/report.json').read_text());after=json.loads((root/'switch-after/report.json').read_text())
 controls={n:(root/'switch-before'/n/'trace.txt').read_bytes()==(root/'switch-after'/n/'trace.txt').read_bytes() for n in ('positive','negative')}
 if not all(controls.values()) or before['runs'][0]['passed'] or not after['passed']:raise ValueError('Switch regression evidence differs')
 return {'qualified':False,'cases':cases,'switchBoundaryRegressionPassed':True,'nonzeroHysteresisControlsByteIdentical':controls,
         'findings':['Relative tolerance tightening reproduces failure; tightening only voltage or current tolerance completes the tested prefix.',
                     'First failure persists with recorded HDL outputs and without bus loads; the reported supply node does not uniquely locate the cause.',
                     'Correcting zero-hysteresis threshold state retention completes the isolated tight replay. The corrected coupled tight run still aborts at a later event.',
                     'Recorded-output replay of the corrected later prefix completes tightly. This does not establish equivalence to the failing live trajectory or prove a bridge defect.'],
         'serviceAcceptance':'Not resumed: static bus input range, coupled refinement and physical driver-model admission remain unmet.',
         'scope':'Ablations change circuit physics and cannot qualify it. Recorded-output replay removes feedback and is diagnostic only. Retained trace summaries include a full-file hash and final samples; raw captures remain local.',
         'reviewSha256':sha(Path(__file__))}

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--collect',type=Path);p.add_argument('--out',type=Path,required=True);p.add_argument('--verify',action='store_true');a=p.parse_args()
 if a.verify:
  for name,h in json.loads((a.out/'manifest.json').read_text()).items():
   if sha(a.out/name)!=h:raise ValueError('Changed transition evidence: '+name)
  if assess(a.out)!=json.loads((a.out/'assessment.json').read_text()):raise ValueError('Stale transition review')
  print('Transition evidence verified; electrical qualification remains open.');return
 if not a.collect:p.error('--collect is required')
 a.out.mkdir(parents=True,exist_ok=False)
 for group,source in GROUPS.items():
  for receipt in sorted((a.collect/source).glob('*/run.json')):
   src=receipt.parent;out=a.out/group/src.name;out.mkdir(parents=True)
   for name in ('run.json','io.cir','ngspice.log'):shutil.copyfile(src/name,out/name)
   trace=next((src/n for n in ('witness.txt','boundary.txt') if (src/n).exists()),None)
   if trace:(out/'trace-summary.json').write_text(json.dumps(extent(trace),indent=2)+'\n')
 for name,source in [('switch-before','bus-switch-before-matched'),('switch-after','bus-switch-corrected')]:shutil.copytree(a.collect/source,a.out/name)
 (a.out/'assessment.json').write_text(json.dumps(assess(a.out),indent=2)+'\n')
 (a.out/'manifest.json').write_text(json.dumps({str(f.relative_to(a.out)):sha(f) for f in sorted(a.out.rglob('*')) if f.is_file()},indent=2)+'\n')
if __name__=='__main__':main()
