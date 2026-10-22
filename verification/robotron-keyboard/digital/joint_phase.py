#!/usr/bin/env python3
"""Qualify the isolated TV80 I/O adapter against retained C firmware captures."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
from qualify import ROOT,BOARD,sha,parse,assess,scenarios
from review import observation_window
from pin_timing import rows,assess as pin_assess,setup_hold
HERE=Path(__file__).resolve().parent

def main():
 p=argparse.ArgumentParser();p.add_argument('capture',type=Path);p.add_argument('--out',type=Path,required=True);p.add_argument('--jobs',type=int,default=2);a=p.parse_args()
 if not 1<=a.jobs<=4:raise ValueError('Use 1–4 workers')
 a.out=a.out.resolve();a.capture=a.capture.resolve();a.out.mkdir(parents=True,exist_ok=True)
 parent=json.loads((a.capture/'assessment.json').read_text())
 for name,digest in parent['sources'].items():
  if sha(ROOT/name)!=digest:raise ValueError('Changed producer '+name)
 if not parent['allScenariosRun'] or [c['scenario'] for c in parent['cases']]!=scenarios():raise ValueError('Incomplete baseline')
 rtl=[*sorted((ROOT/'third_party/cpu/tv80').glob('*.v')),HERE/'tv80_io_candidate.v']
 def run(args,log=None):
  if log:
   with log.open('w') as f:subprocess.run(list(map(str,args)),check=True,stdout=f,timeout=600)
  else:subprocess.run(list(map(str,args)),check=True,timeout=30)
 # Same both-edge instruction fixture, with the candidate in place of tv80n.
 bench=(HERE/'pin_timing.v').read_text().replace('tv80n #(.T2Write(EARLY)) cpu','tv80_io_candidate cpu')
 for signal in ('tstate','iorq','write','i_tv80_core'):bench=bench.replace('cpu.'+signal,'cpu.base.'+signal)
 (a.out/'pin.v').write_text(bench)
 run(['iverilog','-g2012','-s','pin_timing','-o',a.out/'pin.vvp',*rtl,a.out/'pin.v'])
 from pin_timing import PROGRAM,EXPECTED
 (a.out/'program.hex').write_text('\n'.join(f'{b:02x}' for b in PROGRAM)+'\n')
 pins={}
 for case,reset,wait,end in [('write-wait',240,15,19),('no-wait',240,0,0),('read-wait',240,43,48),('reset-write',16,0,0),('reset-read',44,0,0)]:
  log=a.out/(case+'.txt');run(['vvp',a.out/'pin.vvp','+rom='+str(a.out/'program.hex'),f'+reset_at={reset}',f'+wait_at={wait}',f'+wait_end={end}'],log)
  r=pin_assess(rows(log),reset);r['setupHold']=setup_hold(log,r)
  r['postResetRecovery']=[(w['address'],w['data']) for w in r['writes'] if w['startHalfCycle']>=2*(reset+16)]==EXPECTED[:6]
  if not r['postResetRecovery'] or not r['stableDuringWrite'] or not r['resetOutputsInactive']:raise ValueError('Candidate instruction failure '+case)
  if any(not w['knownAtAssertion'] or w['setupObservedHalfCycles']<1 for w in r['setupHold']['writes']):raise ValueError('Candidate setup failure '+case)
  pins[case]=r
 def scenario(case):
  spec=case['scenario'];src=a.capture/spec['id'];dest=a.out/spec['id'];dest.mkdir(exist_ok=True)
  for name,digest in case['artifacts'].items():
   if sha(src/name)!=digest:raise ValueError('Changed capture '+str(src/name))
  # Validate the hex ROM actually used, rather than trusting a filename.
  import hashlib
  if hashlib.sha256(bytes.fromhex((src/'rom.hex').read_text())).hexdigest()!=parent['romSha256']:raise ValueError('ROM mismatch')
  bench=(src/'bench.v').read_text();needle='tv80n cpu('
  if bench.count(needle)!=1:raise ValueError('CPU template changed')
  (dest/'bench.v').write_text(bench.replace(needle,'tv80_io_candidate cpu('))
  run(['iverilog','-g2012','-s','firmware_tb','-o',dest/'bench.vvp',*rtl,BOARD/'chips.v',BOARD/'generated/controller.v',dest/'bench.v'])
  run(['vvp',dest/'bench.vvp','+rom='+str(src/'rom.hex')],dest/'hdl.txt')
  if f"DONE {spec['cycles']}" not in (dest/'hdl.txt').read_text().splitlines():raise ValueError('Incomplete capture')
  c,co=observation_window(parse(src/'c.txt'),spec['cycles']);h,ho=observation_window(parse(dest/'hdl.txt'),spec['cycles'])
  r=assess(spec,c,h);r['outsideObservationInterval']={'c':co,'hdl':ho}
  r['artifacts']={name:sha(dest/name) for name in ('bench.v','hdl.txt')};r['baselineCTraceSha256']=sha(src/'c.txt')
  (dest/'assessment.json').write_text(json.dumps(r,indent=2)+'\n')
  print(spec['id'],r['functionalAgreement'],r['events']['BIT']['rawCycleEquivalent'],flush=True)
  return r
 with ThreadPoolExecutor(max_workers=a.jobs) as pool:results=list(pool.map(scenario,parent['cases']))
 sources=[Path(__file__),HERE/'pin_timing.py',HERE/'pin_timing.v',HERE/'qualify.py',HERE/'review.py',BOARD/'chips.v',BOARD/'generated/controller.v',*rtl]
 report={'schema':1,'profile':'Experimental joint TV80 I/O data and strobe boundary','qualified':False,'productionChanged':False,'romSha256':parent['romSha256'],'baselineSha256':sha(a.capture/'assessment.json'),'sourceHashes':{str(p.relative_to(ROOT)):sha(p) for p in sources},'pinCases':pins,'cases':results,'allScenariosRun':len(results)==len(scenarios()),'functionalAgreement':all(r['functionalAgreement'] for r in results),'serialCycleAgreement':all(r['events']['BIT']['rawCycleEquivalent'] for r in results),'rawCycleAgreement':all(r['rawCycleAgreement'] for r in results),'boundary':'Candidate uses TV80 internal BusB and automatic-wait state. Immediate/ED I/O and firmware coverage do not qualify block I/O, interrupts, external bus arbitration or U880 electrical timing. Fixture cycle labels are not half-cycle equivalence. Reset can truncate output hold; retain that event rather than asserting normal-cycle hold.'}
 report['artifacts']={str(p.relative_to(a.out)):sha(p) for p in sorted(a.out.rglob('*')) if p.is_file() and p.suffix in ('.txt','.v','.hex')}
 (a.out/'assessment.json').write_text(json.dumps(report,indent=2)+'\n')
 print('Candidate:',report['functionalAgreement'],report['serialCycleAgreement'],report['rawCycleAgreement'])
if __name__=='__main__':main()
