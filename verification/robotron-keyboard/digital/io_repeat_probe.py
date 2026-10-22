#!/usr/bin/env python3
"""Observe repeated-I/O flags inside INT/NMI handlers against a hardware oracle."""
import argparse,json,subprocess
from pathlib import Path
from qualify import ROOT,sha
from io_flags_probe import expected as normal_flags
from io_complete_candidate import c_core as old_c,hdl_core as old_hdl,c_half,hdl_wrapper
from io_repeat_candidate import c_core,hdl_core
HERE=Path(__file__).resolve().parent
REFERENCE='https://github.com/hoglet67/Z80Decoder/wiki/Undocumented-Flags'

def expected(op,data,b,c,l,pc):
 f=normal_flags(op&~16,data,b,c,l,0)
 count=(b-1)&255
 term=count
 if f&1:
  term=count+(-1 if data&128 else 1)
  f=(f&~16)|(16 if count%16==(0 if data&128 else 15) else 0)
 if bin(term&7).count('1')%2:f^=4
 return (f&~0x28)|((pc>>8)&0x28)

def vectors():
 for op in (0xb2,0xba,0xb3,0xbb):
  for b,data,c,l,base in [(2,0,0,0,0x100),(2,0x7f,0xff,0xff,0x800),(16,0x7f,0x90,0x90,0x2000),(17,0x80,0x90,0x90,0x2800),(0x80,0xff,0,0,0x100),(0xff,0xff,0xff,0xff,0x2800),(3,0x34,0x80,0x80,0x2000),(17,0xff,0xfe,0xfe,0x800)]:
   for mode in (0,1):yield op,b,data,c,l,base,mode

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,default=ROOT/'build/keyboard-controller-io-repeat');a=ap.parse_args();out=a.out.resolve();out.mkdir(parents=True,exist_ok=True)
 def run(cmd):return subprocess.check_output(list(map(str,cmd)),text=True,timeout=30)
 run(['python3',HERE/'c_read_sampling.py','--out',out/'sampling'])
 vendor=ROOT/'third_party/cpu/tv80'
 for profile in ('old','candidate'):
  folder=out/profile;folder.mkdir(exist_ok=True)
  (folder/'candidate.h').write_text((old_c if profile=='old' else c_core)((ROOT/'third_party/cpu/chips/z80.h').read_text()))
  (folder/'c_read_half.h').write_text(c_half((HERE/'c_read_half.h').read_text()))
  (folder/'tv80_core.v').write_text((old_hdl if profile=='old' else hdl_core)((vendor/'tv80_core.v').read_text()))
  (folder/'tv80_io_candidate.v').write_text(hdl_wrapper((HERE/'tv80_io_candidate.v').read_text()))
  run(['cc','-std=c11','-O2','-Wall','-Wextra','-Werror','-I',folder,HERE/'io_repeat_probe.c','-o',folder/'probe'])
  rtl=[p for p in sorted(vendor.glob('*.v')) if p.name not in ('tv80_core.v','tv80n.v')]+[folder/'tv80_core.v',out/'sampling/tv80n_falling.v',folder/'tv80_io_candidate.v']
  run(['iverilog','-g2012','-s','probe','-o',folder/'probe.vvp',*rtl,HERE/'io_repeat_probe.v'])
 results=[]
 for index,(op,b,data,c,l,base,mode) in enumerate(vectors()):
  mem=bytearray(65536);mem[:3]=bytes([0xc3,base&255,base>>8])
  pre=bytes([0x31,0,0xf0,0x01,c,b,0x21,l,0x80,0xed,0x56,0xfb])
  pc=base+len(pre);mem[base:pc+3]=pre+bytes([0xed,op,0x76]);mem[0x8000+l]=data
  # Save F without flag-modifying instructions; marker proves handler execution.
  handler=bytes.fromhex('f5 e1 7d 32 00 90 3e 42 32 01 90 76')
  for address in (0x38,0x66):mem[address:address+len(handler)]=handler
  folder=out/str(index);folder.mkdir(exist_ok=True);(folder/'program.bin').write_bytes(mem);(folder/'program.hex').write_text('\n'.join(f'{x:02x}' for x in mem)+'\n')
  row={'id':index,'opcode':op,'b':b,'data':data,'registerC':c,'l':l,'pc':pc,'mode':mode,'expected':expected(op,data,b,c,l,pc)}
  for profile in ('old','candidate'):
   for lang in ('c','hdl'):
    cmd=[out/profile/'probe',folder/'program.bin',mode,data] if lang=='c' else ['vvp',out/profile/'probe.vvp','+rom='+str(folder/'program.hex'),f'+mode={mode}',f'+value={data}']
    log=run(cmd);(folder/(profile+'-'+lang+'.txt')).write_text(log)
    row[profile+'-'+lang]=[list(map(int,line.split()[1:])) for line in log.splitlines() if line.startswith('RESULT ')][0]
  results.append(row)
 report={'passed':all(r[k]==[r['expected'],0x42,1,1] for r in results for k in ('candidate-c','candidate-hdl')),'negativeControls':{k:any(r[k][0]!=r['expected'] for r in results) for k in ('old-c','old-hdl')},'cases':results,'reference':REFERENCE,'boundary':'First repeated-I/O iteration interrupted by IM1 or NMI; handler saves all F bits. PC X/Y bits, parity, carry and nibble boundaries covered. Not U880-specific calibration or every interrupt phase.',
 'sources':{str(p.relative_to(ROOT)):sha(p) for p in [Path(__file__),HERE/'io_repeat_candidate.py',HERE/'io_repeat_probe.c',HERE/'io_repeat_probe.v',HERE/'io_complete_candidate.py',HERE/'io_wait_candidate.py',HERE/'io_flags_candidate.py',HERE/'io_flags_probe.py',HERE/'c_read_candidate.py',HERE/'c_read_half.h',HERE/'c_read_sampling.py',HERE/'c_read_half_test.c',HERE/'tv80_io_candidate.v',ROOT/'third_party/cpu/chips/z80.h',*sorted(vendor.glob('*.v'))]},
 'artifacts':{str(p.relative_to(out)):sha(p) for p in sorted(out.rglob('*')) if p.suffix in ('.txt','.h','.v','.hex','.bin')}}
 (out/'assessment.json').write_text(json.dumps(report,indent=2)+'\n');print('Interrupted repeat:',report['passed'],report['negativeControls'])
 for r in results:
  if any(r[k]!=[r['expected'],0x42,1,1] for k in ('candidate-c','candidate-hdl')):print(r)
 if not report['passed'] or not all(report['negativeControls'].values()):raise SystemExit(1)
if __name__=='__main__':main()
