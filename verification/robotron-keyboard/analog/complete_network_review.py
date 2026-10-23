#!/usr/bin/env python3
"""Complete-interval successor to the frozen short-capture evidence reviewer."""
import argparse,json,math,re
from pathlib import Path
from network_refinement_review import artifact,events,text_file,normalized
from host_waveform_comparison import rows,compare_samples
from analog_driver_replay import sha
from network_trace import SIGNALS,PHYSICAL_SIGNALS

def review(directories, expected_end_seconds=.00116):
 if not math.isfinite(expected_end_seconds) or expected_end_seconds<=0:raise ValueError("Invalid required endpoint")
 receipts=[json.loads((p/'run.json').read_text()) for p in directories]
 for p,r in zip(directories,receipts):
  if r['timedOut'] or r['exitCode']!=0 or r['solverDiagnostic']:raise ValueError('Incomplete or failing live run')
  if not r['networkTrace'] or not r['conservativeCap'] or not r['passiveAssembly']:raise ValueError('Wrong correction or observation scope')
  deck=(p/'io.cir').read_text()
  if sha(p/'io.cir')!=r['deckSha256']:raise ValueError('Changed deck')
  for key,base in (('reltol',1e-6),('vntol',1e-9),('abstol',1e-15)):
   values=re.findall(key+r'=([0-9.eE+-]+)',deck)
   if len(values)!=1 or float(values[0])!=base*r['toleranceScale']:raise ValueError('Unexpected tolerance '+key)
 a,b=receipts
 if a.get('physicalDriverTrace',False)!=b.get('physicalDriverTrace',False):raise ValueError('Different physical driver observation')
 selected=a.get('observationSignals') or (PHYSICAL_SIGNALS if a.get('physicalDriverTrace',False) else SIGNALS)
 if a.get('observationSignals')!=b.get('observationSignals'):raise ValueError('Different observation coverage')
 if a.get('observationSignals'):
  for p in directories:
   deck=(p/'io.cir').read_text()
   saved=set(re.findall(r'^\.save (.*)$',deck,re.M)[0].split())
   if not saved.issubset(selected):raise ValueError('Saved observations excluded from comparison')
   if re.findall(r'^wrdata network_witness.txt (.*)$',deck,re.M)!=[' '.join(selected)]:raise ValueError('Trace selection differs from receipt')
 if a.get('adcCrossings',False)!=b.get('adcCrossings',False):raise ValueError('Different ADC crossing mode')
 for key in ('runtime','inputs','sourceDeckSha256','mpfrTransitionBits','mpfrStartNs','method','enabled','matrixBoundarySubstitution'):
  if a[key]!=b[key]:raise ValueError('Different '+key)
 if a['stepNs']!=2*b['stepNs'] or a['toleranceScale']!=2*b['toleranceScale']:raise ValueError('Expected timestep and tolerance halving')
 if normalized((directories[0]/'io.cir').read_text())!=normalized((directories[1]/'io.cir').read_text()):raise ValueError('Physical circuit or stimulus differs')
 observed=compare_samples(*(rows(p/'network_witness.txt',selected,r['stepNs']) for p,r in zip(directories,receipts)))
 if abs(observed['endSeconds']-expected_end_seconds)>max(1e-18,math.ulp(expected_end_seconds)*2):raise ValueError('Required endpoint not reached')
 signals={}
 for name,s in zip(selected,observed['signals']):
  signals[name]={'unit':'A' if (name.startswith('i(') or name.endswith('[i]')) else 'V','maximumAbsoluteDifference':s['maximumDifferenceV'],
                 'timeSeconds':s['timeSeconds'],'coarse':s['coarseV'],'fine':s['fineV'],
                 'meanAbsoluteDifference':s['meanAbsoluteDifferenceV'],'rmsDifference':s['rmsDifferenceV']}
 ev=[events(text_file(artifact(p,'ngspice.log'))) for p in directories]
 same=ev[0]['samples']==ev[1]['samples']
 difference=max(abs(x-y) for x,y in zip(ev[0]['edgeTimesPs'],ev[1]['edgeTimesPs'])) if len(ev[0]['edgeTimesPs'])==len(ev[1]['edgeTimesPs']) else None
 return {'completed':True,'qualified':False,'endSeconds':observed['endSeconds'],'signals':signals,
         'firmwareDataMatches':same,'firmwareLatchesMatch':all(e['latchesMatch'] for e in ev),
         'maximumFirmwareEdgeDifferencePs':difference,'events':ev,
         'artifacts':{label:{n:sha(artifact(p,n)) for n in ('network_witness.txt','ngspice.log','run.json','io.cir')} for label,p in zip(('coarse','fine'),directories)},
         'boundary':'Complete observed interval, piecewise-linear comparison on both sample grids at absolute time. No phase alignment, inferred intersample extrema or physical accuracy budget. Fixture guard is refined with timestep/tolerances; device admission and service/startup qualification remain separate.'}

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('runs',nargs=2,type=Path);p.add_argument('--out',required=True,type=Path);p.add_argument('--end-seconds',required=True,type=float);a=p.parse_args();a.out.write_text(json.dumps(review(a.runs,a.end_seconds),indent=2)+'\n')
