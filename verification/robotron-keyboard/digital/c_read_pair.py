#!/usr/bin/env python3
"""Full firmware sweep of explicit experimental C/HDL I/O read boundaries."""
import argparse,json,re,subprocess,shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from qualify import ROOT,BOARD,sha,parse,assess,scenarios,fixtures
from review import observation_window
from c_read_firmware import shadow
HERE=Path(__file__).resolve().parent

def main():
 p=argparse.ArgumentParser();p.add_argument('--rom',type=Path,required=True);p.add_argument('--out',type=Path,default=ROOT/'build/keyboard-controller-c-read-pair');p.add_argument('--jobs',type=int,default=3);a=p.parse_args()
 if not 1<=a.jobs<=4:raise ValueError('Use 1–4 workers')
 out=a.out.resolve();out.mkdir(parents=True,exist_ok=True);root=out/'shadow';copies=shadow(root);rom=a.rom.resolve()
 if sha(rom)!=json.loads((HERE/'reports/joint-phase/assessment.json').read_text())['romSha256']:raise ValueError('ROM changed')
 # An experimental full-tick caller exercises both halves with the same matrix
 # stimulus. The standalone half-cycle tests supply changing data between them.
 shutil.copyfile(root/'third_party/cpu/chips/z80.h',root/'common/cpu/candidate.h')
 header=(HERE/'c_read_half.h').read_text().replace('#include "candidate.h"','/* Core already included through the shadow CPU header. */')
 (root/'common/cpu/c_read_half.h').write_text(header)
 cpu=(root/'common/cpu/z80.c').read_text().replace('#include "z80.h"','#include "z80.h"\n#undef CHIPS_IMPL\n#include "c_read_half.h"')
 cpu=cpu.replace('  p = z80_tick(&c->cpu, p);','  c_read_half half={c->cpu,p,0};\n  p=c_read_rise(&half,p);')
 cpu=cpu.replace('  c->pins = p;','  p=c_read_fall(&half,p);\n  c->cpu=half.cpu;\n  c->pins = p;')
 # Use the helper reset entry too; no unused static functions in strict builds.
 cpu=cpu.replace('  c->pins = z80_init(&c->cpu);','  c_read_half half; c_read_reset(&half); c->cpu=half.cpu; c->pins=half.pins;')
 (root/'common/cpu/z80.c').write_text(cpu)
 keyboard=(root/'machines/robotron1715m/keyboard.c').read_text()
 guard='  if ((k->cpu.pins & (Z80_IORQ | Z80_RD)) == (Z80_IORQ | Z80_RD))\n    return k->last_read;\n'
 if keyboard.count(guard)!=1:raise ValueError('Input cache guard changed')
 (root/'machines/robotron1715m/keyboard.c').write_text(keyboard.replace(guard,'  /* Experimental 8282 transparency while IORQ is active. */\n'))
 # Regenerate the independently exercised I/O-only falling input latch.
 subprocess.run(['python3',str(HERE/'c_read_sampling.py'),'--out',str(out/'sampling')],check=True)
 rtl=[p for p in sorted((ROOT/'third_party/cpu/tv80').glob('*.v')) if p.name!='tv80n.v']+[out/'sampling/tv80n_falling.v',HERE/'tv80_io_candidate.v',BOARD/'chips.v',BOARD/'generated/controller.v']
 (out/'rom.hex').write_text('\n'.join(f'{x:02x}' for x in rom.read_bytes())+'\n')
 specs=scenarios()+[{'id':'baseline-repeat-release-reset','cycles':4600000,'events':[]}]
 def case(spec):
  dest=out/spec['id'];dest.mkdir(exist_ok=True)
  if spec['id']=='baseline-repeat-release-reset':c=(BOARD/'firmware_probe.c').read_text();v=(BOARD/'firmware_tb.v').read_text()
  else:c,v=fixtures(spec)
  c=c.replace('../../machines/robotron1715m/keyboard.h',str(root/'machines/robotron1715m/keyboard.h')).replace(str(ROOT/'machines/robotron1715m/keyboard.h'),str(root/'machines/robotron1715m/keyboard.h'))
  # BR2 is a CPU reset, not a reset pin on A6 LED latches. Keep their state.
  c,n=re.subn(r'if\(cycle==(\d+)\)robotron_keyboard_init\(&k,rom,NULL,bit\);',r'if(cycle==\1){unsigned held_leds=k.leds;robotron_keyboard_init(&k,rom,NULL,bit);k.leds=held_leds;}',c)
  expected=1 if 'reset' in spec['id'] else 0
  if n!=expected:raise ValueError('Reset fixture changed')
  v=v.replace('tv80n cpu(','tv80_io_candidate cpu(')
  snapshot='  if(cycle>=0&&cycle%200000==199999)$display("LED %0d %0d",cycle,leds);'
  if v.count(snapshot)!=1:raise ValueError('LED observation template changed')
  v=v.replace(snapshot,'')
  v=v.replace(' always @(leds)', ' always @(posedge clk)begin #1;if(cycle>=0&&cycle%200000==199999)$display("LED %0d %0d",cycle,leds);end\n always @(leds)')
  (dest/'probe.c').write_text(c);(dest/'bench.v').write_text(v)
  subprocess.run(['cc','-std=c11','-O2','-Wall','-Wextra','-Werror',str(dest/'probe.c'),str(root/'machines/robotron1715m/keyboard.c'),str(root/'common/cpu/z80.c'),'-o',str(dest/'probe')],check=True)
  subprocess.run(['iverilog','-g2012','-s','firmware_tb','-o',str(dest/'bench.vvp'),*map(str,rtl),str(dest/'bench.v')],check=True)
  for lang,args in [('c',[str(dest/'probe'),str(rom)]),('hdl',['vvp',str(dest/'bench.vvp'),'+rom='+str(out/'rom.hex')])]:
   with (dest/(lang+'.txt')).open('w') as f:subprocess.run(args,check=True,stdout=f,timeout=900)
  cv,co=observation_window(parse(dest/'c.txt'),spec['cycles']);hv,ho=observation_window(parse(dest/'hdl.txt'),spec['cycles'])
  if not cv['LED'] or not hv['LED'] or int(cv['LED'][-1][0])!=(spec['cycles']//200000)*200000-1 or int(hv['LED'][-1][0])!=(spec['cycles']//200000)*200000-1:raise ValueError('Incomplete capture')
  r=assess(spec,cv,hv);r['outsideObservationInterval']={'c':co,'hdl':ho};r['realLedTransitionsEquivalent']=cv['EDGE'][1:]==hv['EDGE'][1:];r['initialLedObservations']={'c':cv['EDGE'][:1],'hdl':hv['EDGE'][:1]}
  r['artifacts']={n:sha(dest/n) for n in ('probe.c','bench.v','c.txt','hdl.txt')}
  print(spec['id'],r['functionalAgreement'],r['events']['BIT']['rawCycleEquivalent'],r['realLedTransitionsEquivalent'],flush=True);return r
 with ThreadPoolExecutor(max_workers=a.jobs) as pool:results=list(pool.map(case,specs))
 sources=[Path(__file__),HERE/'c_read_candidate.py',HERE/'c_read_firmware.py',HERE/'c_read_half.h',HERE/'c_read_sampling.py',HERE/'qualify.py',HERE/'review.py',HERE/'tv80_io_candidate.v',BOARD/'firmware_probe.c',BOARD/'firmware_tb.v',BOARD/'chips.v',BOARD/'generated/controller.v',*(ROOT/f for f in copies),ROOT/'third_party/cpu/chips/z80.h',*sorted((ROOT/'third_party/cpu/tv80').glob('*.v'))]
 report={'qualified':False,'productionChanged':False,'romSha256':sha(rom),'sources':{str(p.relative_to(ROOT)):sha(p) for p in sources},'cases':results,'functionalAgreement':all(r['functionalAgreement'] for r in results),'serialCycleAgreement':all(r['events']['BIT']['rawCycleEquivalent'] for r in results),'realLedTransitionAgreement':all(r['realLedTransitionsEquivalent'] for r in results),'rawCycleAgreement':all(r['rawCycleAgreement'] for r in results),'observationPhase':'Periodic LED snapshots follow the rising edge after HDL nonblocking updates; no edge timestamps are shifted. Initial values remain separate.', 'boundary':'Explicit experimental I/O half-cycle pair, transparent matrix sampling and CPU-only reset retaining LED latches. Initial LED values remain separate observations; C whole-tick fixture BUS logging remains distinct from half-cycle pins. Non-I/O timing, interrupts, arbitration and physical device envelopes are not qualified.'}
 report['generatedSources']={str(p.relative_to(out)):sha(p) for p in sorted(root.rglob('*')) if p.is_file()}
 (out/'assessment.json').write_text(json.dumps(report,indent=2)+'\n')
if __name__=='__main__':main()
