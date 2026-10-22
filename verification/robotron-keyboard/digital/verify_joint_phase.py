#!/usr/bin/env python3
"""Replay candidate assessments from hash-bound traces; rerun the small pin fixture."""
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile
from qualify import ROOT,BOARD,sha,parse,assess,scenarios
from review import observation_window
from pin_timing import rows,assess as pin_assess,setup_hold,EXPECTED
HERE=Path(__file__).resolve().parent
REPORTS=HERE/'reports/joint-phase'

def extract(archive,directory):
 with tarfile.open(archive,'r:gz') as tar:
  for member in tar.getmembers():
   path=directory/member.name
   if not member.isfile() or not path.resolve().is_relative_to(directory.resolve()):raise ValueError('Unsafe archive member')
   path.parent.mkdir(parents=True,exist_ok=True)
   path.write_bytes(tar.extractfile(member).read())

def figure7(path):
 # Figure 7: T1 address, T2 rising control assertion, T3 falling release.
 # TV80 repeats its one-hot state 2 for T1/T2, then uses 4 for TW and 8 for T3.
 trace=rows(path);core=[]
 for line in path.read_text().splitlines():
  f=line.split()
  if f[:1]==['CORE']:core.append([int(x) if x.isdigit() else None for x in f[1:]])
 if len(core)!=len(trace):raise ValueError('Missing internal phase witness')
 checked=0
 for start,row in enumerate(core):
  if row[3]!=1 or start and core[start-1][3]==1:continue
  end=next((i for i in range(start+1,len(core)) if core[i][3]!=1),len(core))
  if not all(p[2] for p in trace[start:end]):continue
  t3=next((i for i in range(start,end) if core[i][2]==8),None)
  if t3 is None:raise ValueError('Missing T3 witness')
  active=[i for i in range(start,end) if trace[i][7]]
  if active!=list(range(start+2,t3+1)):raise ValueError('Figure 7 control phase mismatch')
  for i in range(start,end):
   enabled=int(i in active)
   if trace[i][8:10]!=[enabled*(1-row[4]),enabled*row[4]]:raise ValueError('Read/write strobe disagrees with the I/O phase')
  checked+=1
 if checked<10:raise ValueError('Insufficient I/O phase coverage')

def main():
 subprocess.run(['python3',str(HERE/'verify.py')],check=True)
 for name in ('no-wait-tv80.txt','early-write.txt'):
  try:figure7(HERE/'reports/pin-timing'/name)
  except ValueError as error:
   if 'control phase mismatch' not in str(error):raise
  else:raise ValueError('Phase negative control unexpectedly passed '+name)
 report=json.loads((REPORTS/'assessment.json').read_text());receipt=json.loads((REPORTS/'receipt.json').read_text())
 for name,digest in receipt.items():
  if sha(REPORTS/name)!=digest:raise ValueError('Changed retained artifact '+name)
 for name,digest in report['sourceHashes'].items():
  if sha(ROOT/name)!=digest:raise ValueError('Changed candidate producer '+name)
 if sha(HERE/'reports/assessment.json')!=report['baselineSha256']:raise ValueError('Different baseline')
 if report['qualified'] or report['productionChanged']:raise ValueError('Unsupported qualification claim')
 if not report['allScenariosRun'] or [r['scenario'] for r in report['cases']]!=scenarios():raise ValueError('Missing scenario')
 with tempfile.TemporaryDirectory() as temp:
  root=Path(temp).resolve();candidate=root/'candidate';baseline=root/'baseline'
  extract(REPORTS/'captures.tar.gz',candidate);extract(HERE/'reports/captures.tar.gz',baseline)
  for name,digest in report['artifacts'].items():
   if sha(candidate/name)!=digest:raise ValueError('Changed raw capture '+name)
  results=[]
  for retained in report['cases']:
   spec=retained['scenario'];cpath=baseline/spec['id']/'c.txt';hpath=candidate/spec['id']/'hdl.txt'
   if sha(cpath)!=retained['baselineCTraceSha256']:raise ValueError('Different C trace')
   c,co=observation_window(parse(cpath),spec['cycles']);h,ho=observation_window(parse(hpath),spec['cycles'])
   r=assess(spec,c,h);r['outsideObservationInterval']={'c':co,'hdl':ho}
   r['artifacts']={name:sha(candidate/spec['id']/name) for name in ('bench.v','hdl.txt')};r['baselineCTraceSha256']=sha(cpath)
   if r!=retained:raise ValueError('Candidate result changed '+spec['id'])
   results.append(r)
  for name,value in [('functionalAgreement',all(r['functionalAgreement'] for r in results)),('serialCycleAgreement',all(r['events']['BIT']['rawCycleEquivalent'] for r in results)),('rawCycleAgreement',all(r['rawCycleAgreement'] for r in results))]:
   if report[name]!=value:raise ValueError('Summary changed '+name)
  rtl=[*sorted((ROOT/'third_party/cpu/tv80').glob('*.v')),HERE/'tv80_io_candidate.v']
  subprocess.run(['iverilog','-g2012','-s','pin_timing','-o',str(root/'pin.vvp'),*map(str,rtl),str(candidate/'pin.v')],check=True)
  for case,reset,wait,end in [('write-wait',240,15,19),('no-wait',240,0,0),('read-wait',240,43,48),('reset-write',16,0,0),('reset-read',44,0,0)]:
   path=candidate/(case+'.txt');r=pin_assess(rows(path),reset);r['setupHold']=setup_hold(path,r)
   r['postResetRecovery']=[(w['address'],w['data']) for w in r['writes'] if w['startHalfCycle']>=2*(reset+16)]==EXPECTED[:6]
   if r!=report['pinCases'][case]:raise ValueError('Pin assessment changed '+case)
   with (root/'replay.txt').open('w') as f:subprocess.run(['vvp',str(root/'pin.vvp'),'+rom='+str(candidate/'program.hex'),f'+reset_at={reset}',f'+wait_at={wait}',f'+wait_end={end}'],stdout=f,check=True,timeout=30)
   if rows(root/'replay.txt')!=rows(path):raise ValueError('Pin replay differs '+case)
   if case in ('no-wait','write-wait','read-wait'):
    figure7(root/'replay.txt')
    if any(w['holdObservedHalfCycles']<1 for w in r['setupHold']['writes']):raise ValueError('Normal write hold regression')
 print('Candidate firmware evidence and instruction replay verified; full pin qualification remains open.')
if __name__=='__main__':main()
