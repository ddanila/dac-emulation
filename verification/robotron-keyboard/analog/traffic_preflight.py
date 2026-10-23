#!/usr/bin/env python3
"""Prepare representative live traffic and check its production-C stimulus coverage.

This preflight is not electrical execution or C/HDL agreement.
"""
import argparse,copy,json,re,shutil,subprocess
from pathlib import Path
from io_scenario import load,c_header,observe,contact_source,reset_source,time_ns
from analog_driver_replay import sha
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]

def scenario_deck(deck,scenario):
 for index in range(104):
  deck,n=re.subn(rf'^Vcontact{index} contact{index} 0 .+$',f'Vcontact{index} contact{index} 0 '+contact_source(scenario,index),deck,flags=re.M)
  if n!=1:raise ValueError('Missing contact source')
 deck,n=re.subn(r'^Vfixture_reset fixture_reset 0 .+$','Vfixture_reset fixture_reset 0 '+reset_source(scenario),deck,flags=re.M)
 if n!=1:raise ValueError('Missing reset source')
 deck,n=re.subn(r'^(\.tran\s+\S+)\s+\S+',lambda m:m[1]+f' {time_ns(scenario["cycles"])}n',deck,flags=re.M)
 if n!=1:raise ValueError('Missing transient')
 return deck

def reference_source():
 source=(HERE/'firmware_io_reference.c').read_text()
 source=source.replace('../../../machines/robotron1715m/keyboard.h',str(ROOT/'machines/robotron1715m/keyboard_board.h'))
 source=source.replace('dac_z80_tick(', 'k7658_cpu_tick(')
 old='                robotron_keyboard_init(&keyboard, rom, NULL, bit);'
 if source.count(old)!=1:raise ValueError('Unexpected CPU reset fixture')
 return source.replace(old,'                robotron_keyboard_reset(&keyboard);')

def run_reference(scenario,out,rom):
 out.mkdir(parents=True,exist_ok=False)
 (out/'scenario.json').write_text(json.dumps(scenario,indent=2)+'\n');load(out/'scenario.json')
 (out/'io_scenario.h').write_text(c_header(scenario));(out/'reference.c').write_text(reference_source())
 sources=[out/'reference.c',ROOT/'machines/robotron1715m/keyboard_board.c',ROOT/'machines/robotron1715m/keyboard_cpu.c']
 subprocess.run(['cc','-std=c11','-O2','-Wall','-Wextra','-Werror','-I',str(out),*map(str,sources),'-o',str(out/'reference')],check=True,capture_output=True)
 log=subprocess.check_output([str(out/'reference'),str(rom)],text=True);(out/'reference.log').write_text(log)
 events=[(int(t),int(bit)) for t,bit in re.findall(r'^BIT (\d+) ([01])$',log,re.M)]
 coverage=observe(scenario,events)
 if not coverage['passed']:raise ValueError('Stimulus not exercised by C reference')
 return events,coverage

def run(prepared,out):
 out.mkdir(parents=True,exist_ok=False)
 rom=out/'s600.bin';rom.write_bytes(bytes(int(x,16) for x in (prepared/'s600.hex').read_text().split()))
 if len(rom.read_bytes())!=2048:raise ValueError('Expected 2K ROM')
 cases={n:load(HERE/'scenarios'/f'{n}.json') for n in ('release-repress','modifier')}
 base=load(HERE/'scenarios/single-press.json')
 events,_=run_reference(base,out/'uninterrupted-control',rom)
 burst=[e for e in events if e[0]>=4000]
 if len(burst)<8:raise ValueError('Missing uninterrupted serial burst')
 left,right=burst[5][0],burst[6][0]
 if right-left<20:raise ValueError('No room for reset within observed transmission')
 reset_cycle=(left+right)//2
 interrupted=copy.deepcopy(base);interrupted.update(name='reset during an observed serial burst',cycles=100000)
 interrupted['contacts'] += [{'cycle':30000,'index':61,'closed':False},{'cycle':60000,'index':61,'closed':True}]
 interrupted['resets']=[{'cycle':reset_cycle,'asserted':True},{'cycle':reset_cycle+16,'asserted':False}]
 interrupted['observations']=[{'name':'interrupted transmission','startCycle':4000,'endCycle':reset_cycle,'minimumBits':6},
 {'name':'press after reset','startCycle':60000,'endCycle':100000,'minimumBits':26}]
 cases['reset-during-transmission']=interrupted
 reports={}
 for name,scenario in cases.items():
  p=out/name;events,coverage=run_reference(scenario,p,rom)
  for f in ('io.vvp','s600.hex'):shutil.copyfile(prepared/f,p/f)
  (p/'io.cir').write_text(scenario_deck((prepared/'io.cir').read_text(),scenario))
  reports[name]={'referenceCoverage':coverage,'preparedArtifacts':{n:sha(p/n) for n in ('scenario.json','io_scenario.h','io.cir','io.vvp','s600.hex','reference.c','reference.log')},'electricalExecuted':False}
  if name=='reset-during-transmission':
   before=[e for e in events if e[0]<reset_cycle]
   control=[e for e in burst if e[0]<reset_cycle]
   if before!=control:raise ValueError('Reset changed pre-reset serial prefix')
   if any(reset_cycle<=t<reset_cycle+16 for t,_ in events):raise ValueError('Serial activity during asserted reset')
 report={'preflightPassed':True,'qualified':False,'cases':reports,'resetPlacement':{'cycle':reset_cycle,'uninterruptedNeighborBits':burst[5:7]},
 'romSha256':sha(rom),'sourceSha256':sha(Path(__file__)),
 'productionSources':{str(p.relative_to(ROOT)):sha(p) for p in [ROOT/'common/cpu/z80.h',ROOT/'third_party/cpu/chips/z80.h',HERE/'io_scenario.py',HERE/'firmware_io_reference.c',ROOT/'machines/robotron1715m/keyboard_board.c',ROOT/'machines/robotron1715m/keyboard_cpu.c',ROOT/'machines/robotron1715m/keyboard_board.h',ROOT/'machines/robotron1715m/keyboard_cpu.h',*sorted((ROOT/'machines/robotron1715m/generated/keyboard_cpu').glob('*.h'))]},
 'boundary':'Prepared unchanged physical circuits with new contact/reset stimuli. Production-C coverage only; full live electrical traffic remains gated by boundary convergence and physical-driver admission.'}
 (out/'assessment.json').write_text(json.dumps(report,indent=2)+'\n')
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('prepared',type=Path);p.add_argument('out',type=Path);a=p.parse_args();run(a.prepared.resolve(),a.out.resolve())
