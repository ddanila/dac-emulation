from pathlib import Path
import sys,json,hashlib,bisect
sys.path.insert(0,str(Path('verification/robotron-keyboard/analog').resolve()))
from raw_waveform import header,rows
from trace_io import open_binary
root=Path('build/keyboard-controller-analog');assessment=root/'postreset-adc-assessment.json';review=json.loads(assessment.read_text())
centers=sorted({p['signals'][n]['timeSeconds'] for p in review['comparisons'] for n in review['voltageGate']['failures']})
out=root/'postreset-adc-peaks';out.mkdir(exist_ok=False)
class Hashed:
 def __init__(self,s):self.s=s;self.h=hashlib.sha256();self.size=0
 def read(self,*a):
  x=self.s.read(*a);self.h.update(x);self.size+=len(x);return x
 def readline(self,*a):
  x=self.s.readline(*a);self.h.update(x);self.size+=len(x);return x
reports={}
for step,name in ((25,'postreset-adc-on-25'),(12.5,'postreset-adc-on-12.5'),(6.25,'postreset-adc-on-6.25')):
 folder=root/name;receipt=json.loads((folder/'run.json').read_text());count=receipt['logSummary']['count']
 windows=[[] for _ in centers];before=[None]*len(centers);after=[False]*len(centers);last=None
 with open_binary(folder/'waveform.raw') as stream:
  hashed=Hashed(stream);names,declared=header(hashed);assert declared in (0,count)
  for row in rows(hashed,len(names),count):
   if last is None:assert row[0]==0
   last=row[0]
   for i,t in enumerate(centers):
    if row[0]<t-50e-9:before[i]=row
    elif row[0]<=t+50e-9:
     if not windows[i] and before[i] is not None:windows[i].append(before[i])
     windows[i].append(row)
    elif not after[i]:windows[i].append(row);after[i]=True
  assert abs(last-.00116)<1e-18
  assert {'sha256':hashed.h.hexdigest(),'bytes':hashed.size}==receipt['storage']['waveform.raw']
 data={'stepNs':step,'signals':names,'sourceReceiptSha256':hashlib.sha256((folder/'run.json').read_bytes()).hexdigest(),'windows':[{'centerSeconds':t,'samples':w} for t,w in zip(centers,windows)]}
 (out/f'{step}.json').write_text(json.dumps(data,indent=2)+'\n');reports[str(step)]=data
summary=[]
for i,t in enumerate(centers):
 values={}
 for step,data in reports.items():
  samples=data['windows'][i]['samples'];times=[r[0] for r in samples];j=bisect.bisect_left(times,t)
  if times[j]==t:value=samples[j][1:]
  else:
   a,b=samples[j-1],samples[j];f=(t-a[0])/(b[0]-a[0]);value=[x+f*(y-x) for x,y in zip(a[1:],b[1:])]
  values[step]=dict(zip(data['signals'][1:],value))
 summary.append({'timeSeconds':t,'values':values})
(out/'assessment.json').write_text(json.dumps({'qualified':False,'scope':'Peak-localization excerpts only; full convergence result remains authoritative. Entire source waveforms rehashed while extracting.','fullAssessmentSha256':hashlib.sha256(assessment.read_bytes()).hexdigest(),'centers':summary},indent=2)+'\n')
print(out)
