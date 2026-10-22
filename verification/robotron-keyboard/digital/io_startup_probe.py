#!/usr/bin/env python3
"""Explicit LED validity contract: arbitrary power-on bits become known on IORQ."""
import argparse,json,subprocess
from pathlib import Path
from qualify import ROOT,BOARD,sha
HERE=Path(__file__).resolve().parent

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--rom',type=Path,required=True);ap.add_argument('--firmware',type=Path,default=ROOT/'build/keyboard-controller-io-final-firmware');ap.add_argument('--out',type=Path,default=ROOT/'build/keyboard-controller-io-startup');a=ap.parse_args();out=a.out.resolve();out.mkdir(parents=True,exist_ok=True);source=a.firmware.resolve();root=source/'shadow'
 def run(cmd):return subprocess.check_output(list(map(str,cmd)),text=True,timeout=30)
 c='''#include "HEADER"
#include <stdio.h>
#include <stdlib.h>
static unsigned cycle;
static void bit(void *u,unsigned v){(void)u;printf("BIT %u %u\\n",cycle,v);}
int main(int argc,char **argv){
 if(argc!=3)return 2;
 unsigned char rom[2048];FILE *f=fopen(argv[1],"rb");if(!f)return 2;
 size_t n=fread(rom,1,sizeof rom,f);fclose(f);if(n!=2048)return 2;
 robotron_keyboard k;robotron_keyboard_init(&k,rom,0,bit);k.leds=atoi(argv[2]);
 printf("INIT %u\\n",k.leds);int known=0,selected=0;
 for(cycle=0;cycle<20000;cycle++){
  dac_z80_tick(&k.cpu,0,0);int io=!!(k.cpu.pins&Z80_IORQ);
  if(io&&!selected){printf("IO %u %u %u\\n",cycle,Z80_GET_ADDR(k.cpu.pins),k.leds);
   if(!known){known=1;printf("KNOWN %u %u\\n",cycle,k.leds);}}
  selected=io;
 }
 return 0;
}
'''.replace('HEADER',str(root/'machines/robotron1715m/keyboard.h'))
 (out/'probe.c').write_text(c)
 run(['cc','-std=c11','-O2','-Wall','-Wextra','-Werror',out/'probe.c',root/'machines/robotron1715m/keyboard.c',root/'common/cpu/z80.c','-o',out/'probe'])
 h=(BOARD/'firmware_tb.v').read_text().replace('tv80n cpu(','tv80_io_candidate cpu(').replace('if(cycle==4600000)$finish;','if(cycle==20000)$finish;')
 h=h.replace(' initial begin\n', ''' integer initial_leds;reg known=0;
 initial begin
  if(!$value$plusargs("initial_leds=%d",initial_leds))$fatal(1,"initial LEDs missing");
  #1;if(initial_leds>=0)begin board.A6.first.q=initial_leds[1];board.A6.second.q=initial_leds[0];end
  #1;$display("INIT %b",leds);
 end
 always @(negedge iorq_n)if(cpu_reset_n)begin
  #1;$display("IO %0d %0d %0d",cycle,address,leds);
  if(!known)begin known=1;$display("KNOWN %0d %0d",cycle,leds);end
 end
 initial begin
''',1)
 (out/'probe.v').write_text(h)
 vendor=ROOT/'third_party/cpu/tv80';rtl=[p for p in sorted(vendor.glob('*.v')) if p.name not in ('tv80_core.v','tv80n.v')]+[source/'tv80_core.v',source/'tv80_io_candidate.v',source/'sampling/tv80n_falling.v',BOARD/'chips.v',BOARD/'generated/controller.v']
 run(['iverilog','-g2012','-s','firmware_tb','-o',out/'probe.vvp',*rtl,out/'probe.v'])
 results=[];reference=None
 for initial in (-1,0,1,2,3):
  row={'initial':initial}
  for lang in ('c','hdl'):
   if lang=='c' and initial<0:continue
   cmd=[out/'probe',a.rom.resolve(),initial] if lang=='c' else ['vvp',out/'probe.vvp','+rom='+str(source/'rom.hex'),f'+initial_leds={initial}']
   log=run(cmd);(out/f'{lang}-{initial}.txt').write_text(log)
   visible=[line for line in log.splitlines() if line.startswith(('IO ','KNOWN ','BIT '))]
   known=[line for line in visible if line.startswith('KNOWN ')]
   row[lang]={'known':known,'observableTrace':visible}
   if reference is None:reference=visible
   row[lang+'Agrees']=bool(known) and visible==reference
  results.append(row)
 report={'passed':all(v for r in results for k,v in r.items() if k.endswith('Agrees')),'cases':results,'romSha256':sha(a.rom),'contract':{'initialLedValidity':False,'knownAfter':'First ordinary IORQ assertion clocks A6; its resulting value is compared at the settled observation point.','cpuReset':'Does not clear A6; retain a previously known latch value.','scope':'All binary initial latch states and HDL unknown startup converge without shifting timestamps. Initial C zero is a software default, not a claimed physical power-on value.'},
 'sources':{str(p.relative_to(ROOT)):sha(p) for p in [Path(__file__),BOARD/'firmware_tb.v',BOARD/'chips.v',BOARD/'generated/controller.v',*sorted(vendor.glob('*.v'))]},
 'candidateSources':{str(p.relative_to(source)):sha(p) for p in [source/'tv80_core.v',source/'tv80_io_candidate.v',source/'sampling/tv80n_falling.v',*sorted(root.rglob('*.c')),*sorted(root.rglob('*.h'))]},
 'artifacts':{p.name:sha(p) for p in sorted(out.iterdir()) if p.suffix in ('.c','.v','.txt')}}
 (out/'assessment.json').write_text(json.dumps(report,indent=2)+'\n');print('Startup validity:',report['passed'])
 if not report['passed']:
  for row in results:print(row)
  raise SystemExit(1)
if __name__=='__main__':main()
