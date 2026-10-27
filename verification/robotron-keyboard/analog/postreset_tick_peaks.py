#!/usr/bin/env python3
"""Extract hash-bound peak windows without changing the full convergence gate."""
import argparse,bisect,hashlib,json,lzma,math
from pathlib import Path
from raw_waveform import header,rows
from trace_io import open_binary
from ttl7406_probe import sha
from live_raw_review import signal_name
PAIRS={'coarseFine':('coarse','fine'),'fineFinest':('fine','finest')}
HALF_WINDOW=50e-9

class Hashed:
    def __init__(self,stream):self.stream=stream;self.digest=hashlib.sha256();self.size=0
    def read(self,*args):
        value=self.stream.read(*args);self.digest.update(value);self.size+=len(value);return value
    def readline(self,*args):
        value=self.stream.readline(*args);self.digest.update(value);self.size+=len(value);return value


def targets(assessment):
    return sorted({assessment['comparisons'][pair]['signals'][node]['timeSeconds']
                   for pair in PAIRS for node in assessment['voltageGate']['failures']})


def interpolate(samples,column,t):
    times=[row[0] for row in samples];i=bisect.bisect_left(times,t)
    if i==len(times) or (not i and times[i]!=t):raise ValueError('Peak outside retained window')
    if times[i]==t:
        return dict(value=samples[i][column],exactSample=True,bracketSeconds=[t,t],bracketValues=[samples[i][column]]*2)
    a,b=samples[i-1],samples[i];fraction=(t-a[0])/(b[0]-a[0])
    return dict(value=a[column]+fraction*(b[column]-a[column]),exactSample=False,
                bracketSeconds=[a[0],b[0]],bracketValues=[a[column],b[column]])


def crossings(samples,column,threshold):
    found=[]
    for a,b in zip(samples,samples[1:]):
        x,y=a[column],b[column]
        if x<threshold<=y or y<threshold<=x:
            found.append(dict(timeSeconds=a[0]+(threshold-x)*(b[0]-a[0])/(y-x),rising=y>x))
    return found


def review(root):
    full=json.loads((root/'full-assessment.json').read_text());centers=targets(full);data={}
    for label in ('coarse','fine','finest'):
        with lzma.open(root/(label+'.json.xz'),'rt') as f:data[label]=json.load(f)
        d=data[label];r=json.loads((root/(label+'-run.json')).read_text())
        if d['sourceReceiptSha256']!=sha(root/(label+'-run.json')) or d['fullWaveform']!=r['storage']['waveform.raw']:raise ValueError('Changed source binding')
        if [w['centerSeconds'] for w in d['windows']]!=centers:raise ValueError('Missing peak windows')
        if d['stepNs']!=r['stepNs']:raise ValueError('Changed timestep')
        for window in d['windows']:
            samples=window['samples'];t=window['centerSeconds']
            if not samples or samples[0][0]>=t-HALF_WINDOW or samples[-1][0]<=t+HALF_WINDOW:raise ValueError('Missing window boundary brackets')
            if any(len(row)!=len(d['signals']) or not all(map(math.isfinite,row)) for row in samples):raise ValueError('Invalid retained samples')
            if any(b[0]<=a[0] for a,b in zip(samples,samples[1:])):raise ValueError('Nonmonotonic excerpt')
    peaks=[]
    for pair,(left,right) in PAIRS.items():
        for node in full['voltageGate']['failures']:
            original=full['comparisons'][pair]['signals'][node];t=original['timeSeconds'];index=centers.index(t)
            support={};edges={}
            for label in (left,right):
                d=data[label];column=d['signals'].index(node);samples=d['windows'][index]['samples']
                support[label]=interpolate(samples,column,t)
                edges[label]={str(level):crossings(samples,column,level) for level in (1.4,2.5,3.5)}
            difference=abs(support[left]['value']-support[right]['value'])
            if not math.isclose(difference,original['maximumAbsoluteDifference'],rel_tol=1e-10,abs_tol=1e-14):raise ValueError('Excerpt does not reproduce full comparison peak')
            delays={}
            for threshold in ('1.4','2.5','3.5'):
                a,b=edges[left][threshold],edges[right][threshold]
                if len(a)==len(b)==1 and a[0]['rising']==b[0]['rising']:
                    delays[threshold]=b[0]['timeSeconds']-a[0]['timeSeconds']
            peaks.append(dict(pair=pair,node=node,timeSeconds=t,maximumDifferenceV=difference,support=support,
                              thresholdCrossings=edges,matchedCrossingDifferenceSeconds=delays))
    return dict(qualified=False,fullAssessmentSha256=sha(root/'full-assessment.json'),peaks=peaks,
                scope='Retained bracketing samples reproduce every failing-node peak in both refinement pairs on absolute time. Crossing offsets describe piecewise-linear excerpts only; no time alignment, convergence waiver or intersample truth claim.',
                notEstablished=['Cause of trajectory or interpolation differences','Numerical convergence and acceptance of changed firmware timing'])


def extract(assessment,folders,out):
    out.mkdir(exist_ok=False);full=json.loads(assessment.read_text());(out/'full-assessment.json').write_bytes(assessment.read_bytes());centers=targets(full)
    if not centers:raise ValueError('No failing peaks')
    for label,folder in folders.items():
        receipt=json.loads((folder/'run.json').read_text());count=receipt['logSummary']['count']
        if sha(folder/'run.json')!=full['receipts'][label]:raise ValueError('Wrong reviewed capture')
        windows=[[] for _ in centers];before=[None]*len(centers);after=[False]*len(centers);last=None
        with open_binary(folder/'waveform.raw') as stream:
            hashed=Hashed(stream);names,declared=header(hashed)
            if declared not in (0,count):raise ValueError('Wrong full sample count')
            for row in rows(hashed,len(names),count):
                if last is None and row[0]!=0:raise ValueError('Missing waveform start')
                last=row[0]
                for i,t in enumerate(centers):
                    if row[0]<t-HALF_WINDOW:before[i]=row
                    elif row[0]<=t+HALF_WINDOW:
                        if not windows[i] and before[i] is not None:windows[i].append(before[i])
                        windows[i].append(row)
                    elif not after[i]:windows[i].append(row);after[i]=True
            observed=dict(sha256=hashed.digest.hexdigest(),bytes=hashed.size)
            if observed!=receipt['storage']['waveform.raw'] or last!=receipt['endSeconds']:raise ValueError('Changed or incomplete waveform')
        (out/(label+'-run.json')).write_bytes((folder/'run.json').read_bytes())
        normalized=list(map(signal_name,names));selected=['time',*sorted(full['voltageGate']['failures'])]
        columns=[normalized.index(n) for n in selected]
        data=dict(stepNs=receipt['stepNs'],signals=selected,sourceReceiptSha256=sha(folder/'run.json'),fullWaveform=observed,
                  windows=[dict(centerSeconds=t,samples=[[row[j] for j in columns] for row in w]) for t,w in zip(centers,windows)])
        with lzma.open(out/(label+'.json.xz'),'wt') as f:json.dump(data,f,separators=(',',':'));f.write('\n')
    (out/'assessment.json').write_text(json.dumps(review(out),indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--check',type=Path)
    for n in ('assessment','coarse','fine','finest','out'):p.add_argument('--'+n,type=Path)
    a=p.parse_args()
    if a.check:
        if review(a.check)!=json.loads((a.check/'assessment.json').read_text()):raise ValueError('Changed peak assessment')
    else:
        if not all((a.assessment,a.coarse,a.fine,a.finest,a.out)):p.error('Need complete reviewed captures and fresh output')
        extract(a.assessment,{n:getattr(a,n) for n in ('coarse','fine','finest')},a.out)
