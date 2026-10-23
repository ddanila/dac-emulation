#!/usr/bin/env python3
"""Retain causal transition windows and undefined intent without masking waveform errors."""
import argparse,hashlib,json,re
from pathlib import Path
from network_refinement_review import artifact,text_file
from trace_io import open_text
from prepare_boundary_trace import SIGNALS

def observations(log):
 events=[]
 for match in re.finditer(r'BOUNDARY_PS ([^\r\n]+)',log):
  fields=match[1].split()
  if len(fields)!=8:raise ValueError('Malformed boundary observation')
  t=int(fields[0]);states=fields[1:5]
  if any(s not in ('0','1','x','z') for s in states):raise ValueError('Invalid boundary state')
  item={'timePs':t,'d0':states[0],'dataSink':states[1],'clockSink':states[2],'wrN':states[3],
        'address':fields[5],'busLow':fields[6],'busHigh':fields[7]}
  if events and t<events[-1]['timePs']:raise ValueError('Boundary time went backwards')
  if events and t==events[-1]['timePs']:
   if events[-1]!=item:raise ValueError('Inconsistent settled observation')
  else:events.append(item)
 if not events:raise ValueError('Missing boundary observations')
 return events

def undefined_intervals(events,end_ps):
 intervals=[];start=None
 for e in events:
  unknown=e['dataSink'] in ('x','z')
  if unknown and start is None:start=e['timePs']
  if not unknown and start is not None:
   intervals.append([start,e['timePs']]);start=None
 if start is not None:intervals.append([start,end_ps])
 return intervals

def raw_sha(path):
 h=hashlib.sha256()
 with open_text(path) as stream:
  for chunk in iter(lambda:stream.read(1024*1024),''):h.update(chunk.encode())
 return h.hexdigest()

def review(directory,baseline,comparison):
 r=json.loads((directory/'run.json').read_text())
 if r['timedOut'] or r['exitCode'] or r['solverDiagnostic']:raise ValueError('Failed observer run')
 control=json.loads((baseline/'run.json').read_text())
 for k in ('runtime','stepNs','toleranceScale','mpfrStartNs','fixtureCrossingGuardPs','enabled','method','conservativeCap','passiveAssembly'):
  if r[k]!=control[k]:raise ValueError('Different observer control '+k)
 hashes={n:raw_sha(directory/n) for n in ('witness.txt','network_witness.txt')}
 if any(h!=raw_sha(baseline/n) for n,h in hashes.items()):raise ValueError('Observer changed original waveforms')
 events=observations(text_file(artifact(directory,'ngspice.log')))
 if any(e['d0']!=e['dataSink'] or e['wrN']!=e['clockSink'] for e in events):raise ValueError('Unexpected settled output mapping')
 windows=[]
 for name in ('v(n_TA_DATEN)','i(L1.4)','v(data_intent)'):
  t=comparison['signals'][name]['timeSeconds']
  windows.append({'signal':name,'maximumDifference':comparison['signals'][name]['maximumAbsoluteDifference'],
   'centerSeconds':t,'events':[e for e in events if abs(e['timePs']*1e-12-t)<=40e-9],'samples':[]})
 with open_text(directory/'boundary_witness.txt') as stream:
  if stream.readline().split()!=['time',*SIGNALS]:raise ValueError('Wrong observer header')
  for line in stream:
   row=list(map(float,line.split()))
   if len(row)!=1+len(SIGNALS):raise ValueError('Invalid observer row')
   for window in windows:
    if abs(row[0]-window['centerSeconds'])<=40e-9:window['samples'].append(row)
  end=row[0]
 if abs(end-.00116)>1e-18 or any(not w['samples'] or not w['events'] for w in windows):raise ValueError('Missing observation window')
 return {'observerWaveformsUnchanged':True,'waveformSha256':hashes,'qualified':False,'endSeconds':end,
 'outputMappingsMatch':True,'unknownDataIntentIntervalsPs':undefined_intervals(events,round(end*1e12)),
 'signals':SIGNALS,'windows':windows,'events':events,
 'boundary':'All extrema retained at absolute time. Unknown is propagated from voltage-derived D0 through A1 intent; the DAC undefined value equals the ideal switch threshold. This is not a calibrated physical transfer curve. HDL timestamps precede the declared cosimulation output delay; no trace alignment is applied.'}
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory',type=Path);p.add_argument('baseline',type=Path);p.add_argument('comparison',type=Path);p.add_argument('--out',type=Path,required=True);a=p.parse_args();a.out.write_text(json.dumps(review(a.directory,a.baseline,json.loads(a.comparison.read_text())),indent=2)+'\n')
