#!/usr/bin/env python3
"""Compare both-edge I/O pins without shifting either fixture's clock labels."""
import argparse,json,subprocess
from pathlib import Path
from qualify import ROOT,sha
from pin_timing import PROGRAM,rows
from io_repeat_candidate import c_core,hdl_core
from io_complete_candidate import c_half,hdl_wrapper
HERE=Path(__file__).resolve().parent
DRIVER=r'''
#define CHIPS_IMPL
#include <c_read_half.h>
#include <stdio.h>
#include <stdlib.h>
int main(int argc,char **argv){
 if(argc!=5)return 2;
 int reset_at=atoi(argv[2]),wait_at=atoi(argv[3]),wait_end=atoi(argv[4]);
 unsigned char mem[65536]={0};FILE *f=fopen(argv[1],"rb");if(!f)return 2;
 size_t n=fread(mem,1,sizeof mem,f);fclose(f);if(!n)return 2;
 c_read_half cpu;c_read_reset(&cpu);uint64_t p=cpu.pins;
 for(int c=0;c<400;c++){
  int reset=c>=reset_at&&c<reset_at+16,wait=c>=wait_at&&c<wait_end;
  if(c==reset_at){c_read_reset(&cpu);p=cpu.pins;}
  for(int edge=0;edge<2;edge++){
   if(!reset){
    if(wait)p|=Z80_WAIT;else p&=~Z80_WAIT;
    p=edge?c_read_fall(&cpu,p):c_read_rise(&cpu,p);
    if((p&(Z80_MREQ|Z80_RD))==(Z80_MREQ|Z80_RD)){Z80_SET_DATA(p,mem[Z80_GET_ADDR(p)]);}
    if((p&(Z80_IORQ|Z80_RD))==(Z80_IORQ|Z80_RD)){Z80_SET_DATA(p,0xa6);}
    if((p&(Z80_MREQ|Z80_WR))==(Z80_MREQ|Z80_WR))mem[Z80_GET_ADDR(p)]=Z80_GET_DATA(p);
   }
   printf("PIN %d %d %d %d %u %u %d %d %d %d\n",c,edge,!reset,!wait,Z80_GET_ADDR(p),Z80_GET_DATA(p),!!(p&Z80_MREQ),!!(p&Z80_IORQ),!!(p&Z80_RD),!!(p&Z80_WR));
  }
 }
 return 0;
}
'''

def compare(c,h):
 mismatches=[]
 for cr,hr in zip(c,h):
  # Ordinary I/O selection plus its address/data; no timestamp normalization.
  if cr[7] or hr[7]:
   if cr!=hr:mismatches.append({'c':cr,'hdl':hr})
 return {'ioPinsAgree':not mismatches,'mismatches':mismatches,'ioHalfEdges':sum(bool(c[7] or h[7]) for c,h in zip(c,h))}

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--require-pass',action='store_true');ap.add_argument('--out',type=Path,default=ROOT/'build/keyboard-controller-io-pins');a=ap.parse_args();out=a.out.resolve();out.mkdir(parents=True,exist_ok=True)
 def run(cmd):return subprocess.check_output(list(map(str,cmd)),text=True,timeout=30)
 (out/'candidate.h').write_text(c_core((ROOT/'third_party/cpu/chips/z80.h').read_text()));(out/'c_read_half.h').write_text(c_half((HERE/'c_read_half.h').read_text()));(out/'probe.c').write_text(DRIVER)
 run(['cc','-std=c11','-O2','-Wall','-Wextra','-Werror','-I',out,out/'probe.c','-o',out/'probe'])
 h=(HERE/'pin_timing.v').read_text().replace('tv80n #(.T2Write(EARLY)) cpu(', 'tv80_io_candidate cpu(')
 for signal in ('tstate','iorq','write','i_tv80_core'):h=h.replace('cpu.'+signal,'cpu.base.'+signal)
 (out/'probe.v').write_text(h)
 run(['python3',HERE/'c_read_sampling.py','--out',out/'sampling'])
 vendor=ROOT/'third_party/cpu/tv80';(out/'tv80_core.v').write_text(hdl_core((vendor/'tv80_core.v').read_text()));(out/'tv80_io_candidate.v').write_text(hdl_wrapper((HERE/'tv80_io_candidate.v').read_text()))
 rtl=[p for p in sorted(vendor.glob('*.v')) if p.name not in ('tv80_core.v','tv80n.v')]+[out/'tv80_core.v',out/'tv80_io_candidate.v',out/'sampling/tv80n_falling.v']
 run(['iverilog','-g2012','-s','pin_timing','-o',out/'probe.vvp',*rtl,out/'probe.v'])
 (out/'program.bin').write_bytes(PROGRAM);(out/'program.hex').write_text('\n'.join(f'{x:02x}' for x in PROGRAM)+'\n')
 results=[]
 for name,reset,wait,end in [('plain',240,0,0),('write-wait',240,15,19),('read-wait',240,43,48),('reset-write',16,0,0),('reset-read',44,0,0)]:
  for lang in ('c','hdl'):
   cmd=[out/'probe',out/'program.bin',reset,wait,end] if lang=='c' else ['vvp',out/'probe.vvp','+rom='+str(out/'program.hex'),f'+reset_at={reset}',f'+wait_at={wait}',f'+wait_end={end}']
   (out/(name+'-'+lang+'.txt')).write_text(run(cmd))
  r=compare(rows(out/(name+'-c.txt')),rows(out/(name+'-hdl.txt')));r['id']=name;results.append(r)
 report={'passed':all(r['ioPinsAgree'] and r['ioHalfEdges'] for r in results),'cases':results,'boundary':'Same labelled rising/falling fixture observations for ordinary I/O. Memory, inactive-address, startup and interrupt-acknowledge pins are outside this comparison; no rows or timestamps are shifted.',
 'sources':{str(p.relative_to(ROOT)):sha(p) for p in [Path(__file__),HERE/'pin_timing.py',HERE/'pin_timing.v',HERE/'io_repeat_candidate.py',HERE/'io_complete_candidate.py',HERE/'io_wait_candidate.py',HERE/'io_flags_candidate.py',HERE/'c_read_candidate.py',HERE/'c_read_half.h',HERE/'c_read_sampling.py',HERE/'c_read_half_test.c',HERE/'tv80_io_candidate.v',ROOT/'third_party/cpu/chips/z80.h',*sorted(vendor.glob('*.v'))]},
 'artifacts':{str(p.relative_to(out)):sha(p) for p in sorted(out.rglob('*')) if p.suffix in ('.txt','.h','.v','.c','.hex','.bin')}}
 (out/'assessment.json').write_text(json.dumps(report,indent=2)+'\n')
 print([(r['id'],r['ioPinsAgree'],len(r['mismatches'])) for r in results])
 if a.require_pass and not report['passed']:raise SystemExit('I/O pin mismatch')
if __name__=='__main__':main()
