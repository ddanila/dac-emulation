#!/usr/bin/env python3
"""Compare complete live network traces at absolute time, without physical qualification."""
import argparse,json,lzma,re
from pathlib import Path
from host_waveform_comparison import rows,compare_samples
from analog_driver_replay import sha
from network_trace import SIGNALS

def text_file(path):
 return (lzma.decompress(path.read_bytes()).decode() if path.suffix=='.xz' else path.read_text())

def artifact(directory,name):
 path=directory/name
 return path if path.exists() else path.with_name(path.name+'.xz')

def normalized(deck):
 deck,count=re.subn(r'^Vfixture_crossing_grid fixture_crossing_grid 0 PWL\(\n(?:\+ [0-9.]+n 0\n)+\+ \)\n','',deck,flags=re.M)
 if count!=1:raise ValueError('Expected analytic fixture crossing grid')
 deck,count=re.subn(r'^(\.tran) [0-9.]+n ',r'\1 STEP ',deck,flags=re.M)
 if count!=1:raise ValueError('Expected one transient')
 for key in ('reltol','vntol','abstol'):
  deck,count=re.subn(r'('+key+r'=)[0-9.eE+-]+',r'\1VALUE',deck)
  if count!=1:raise ValueError('Missing solver tolerance')
 return deck

def events(log):
 edge=[int(x) for x in re.findall(r'BUS_EDGE_PS (\d+)',log)]
 samples=[s.split() for s in re.findall(r'BUS_SAMPLE ([^\r\n]+)',log)]
 latches=[s.split() for s in re.findall(r'BUS_LATCH ([^\r\n]+)',log)]
 if not edge or len(edge)!=len(samples) or len(samples)!=len(latches):raise ValueError('Missing bus observations')
 if any(b<=a for a,b in zip(edge,edge[1:])):raise ValueError('Nonmonotonic bus edges')
 if any(len(s)!=6 for s in samples) or any(len(s)!=3 for s in latches):raise ValueError('Malformed bus observation')
 return {'edgeTimesPs':edge,'samples':[s[1:] for s in samples],
         'latchesMatch':all(a[1].lower()==a[2].lower() and re.fullmatch('[0-9a-fA-F]{2}',a[2]) for a in latches)}

def review(directories):
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
 for key in ('runtime','inputs','sourceDeckSha256','mpfrTransitionBits','mpfrStartNs','method'):
  if a[key]!=b[key]:raise ValueError('Different '+key)
 if a['stepNs']!=2*b['stepNs'] or a['toleranceScale']!=2*b['toleranceScale']:raise ValueError('Expected timestep and tolerance halving')
 if normalized((directories[0]/'io.cir').read_text())!=normalized((directories[1]/'io.cir').read_text()):raise ValueError('Physical circuit or stimulus differs')
 observed=compare_samples(*(rows(p/'network_witness.txt',SIGNALS,r['stepNs']) for p,r in zip(directories,receipts)))
 if abs(observed['endSeconds']-.00116)>1e-18:raise ValueError('Required endpoint not reached')
 signals={}
 for name,s in zip(SIGNALS,observed['signals']):
  signals[name]={'unit':'A' if name.startswith('i(') else 'V','maximumAbsoluteDifference':s['maximumDifferenceV'],
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
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('runs',nargs=2,type=Path);p.add_argument('--out',required=True,type=Path);a=p.parse_args();a.out.write_text(json.dumps(review(a.runs),indent=2)+'\n')
