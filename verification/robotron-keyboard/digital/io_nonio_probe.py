#!/usr/bin/env python3
"""Non-I/O regression isolation, not a general CPU conformance claim."""
import argparse,json,subprocess
from pathlib import Path
from qualify import ROOT,sha
from c_read_candidate import generate
from io_flags_candidate import generate as flags_generate
from io_wait_candidate import c_generate,hdl_generate,core_generate
HERE=Path(__file__).resolve().parent

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,default=ROOT/'build/keyboard-controller-io-nonio');a=ap.parse_args();out=a.out.resolve();out.mkdir(parents=True,exist_ok=True)
 def run(cmd):return subprocess.check_output(list(map(str,cmd)),text=True,timeout=30)
 run(['python3',HERE/'c_read_sampling.py','--out',out/'sampling'])
 vendor=ROOT/'third_party/cpu/tv80'
 for profile in ('original','candidate'):
  folder=out/profile;folder.mkdir(exist_ok=True)
  c=(ROOT/'third_party/cpu/chips/z80.h').read_text()
  (folder/'candidate.h').write_text(c if profile=='original' else generate(c))
  (folder/'c_read_half.h').write_text(c_generate((HERE/'c_read_half.h').read_text()))
  run(['cc','-std=c11','-O2','-Wall','-Wextra','-Werror',*(['-DHALF'] if profile=='candidate' else []),'-I',folder,HERE/'io_nonio_probe.c','-o',folder/'probe'])
  rtl=sorted(vendor.glob('*.v'))
  if profile=='candidate':
   (folder/'tv80_core.v').write_text(core_generate(flags_generate((vendor/'tv80_core.v').read_text())))
   (folder/'tv80_io_candidate.v').write_text(hdl_generate((HERE/'tv80_io_candidate.v').read_text()))
   rtl=[p for p in rtl if p.name not in ('tv80_core.v','tv80n.v')]+[folder/'tv80_core.v',folder/'tv80_io_candidate.v',out/'sampling/tv80n_falling.v']
  run(['iverilog','-g2012','-s','probe','-DCPU='+('tv80n' if profile=='original' else 'tv80_io_candidate'),'-o',folder/'probe.vvp',*rtl,HERE/'io_nonio_probe.v'])
 results=[]
 for im,opcode in [(0,0x46),(1,0x56),(2,0x5e)]:
  mem=bytearray(65536)
  # Register/memory/indexed/stack operations before HALT; ISR modifies A and RAM.
  program=bytes.fromhex('31 00 f0 21 00 80 36 5a dd 21 00 80 dd 7e 00 f5 f1 3e 81 ed 47')+bytes([0xed,opcode,0xfb,0x76,0x32,0x01,0x80,0x76])
  mem[:len(program)]=program
  for address in (0x38,0x66):mem[address:address+8]=bytes.fromhex('3e 6d 32 02 80 ed 45 00')
  mem[0x81ff:0x8201]=bytes([0x38,0])
  (out/'program.bin').write_bytes(mem)
  (out/'program.hex').write_text('\n'.join(f'{x:02x}' for x in mem)+'\n')
  for mode in range(5):
   row={'im':im,'mode':mode};logs={}
   for lang in ('c','hdl'):
    if lang=='c' and mode==4:continue  # CHIPS exposes no BUSRQ/BUSACK pins.
    for profile in ('original','candidate'):
     folder=out/profile
     cmd=[folder/'probe',out/'program.bin',mode] if lang=='c' else ['vvp',folder/'probe.vvp','+rom='+str(out/'program.hex'),f'+mode={mode}']
     log=run(cmd);path=folder/f'{lang}-im{im}-mode{mode}.txt';path.write_text(log)
     logs[profile]=[l for l in log.splitlines() if l.startswith(('PIN ','RESULT '))]
    row[lang+'Unchanged']=logs['original']==logs['candidate']
    values=list(map(int,logs['candidate'][-1].split()[1:]))
    row[lang+'Result']=values
    row[lang+'Expected']=values[0]==0x5a and values[2]==(0x6d if mode in (1,2) else 0) and (mode!=1 or values[3]>0) and (mode!=4 or values[4]>0)
   results.append(row)
 report={'passed':all(all(v for k,v in r.items() if k.endswith(('Unchanged','Expected'))) for r in results),'cases':results,
 'scope':'Same-core before/after pin regression for memory, indexed access, stack, HALT, IM0/1/2, NMI and memory WAIT. HDL BUSRQ/BUSACK exercised; CHIPS has no arbitration interface. Does not prove cross-core raw-pin equivalence or interrupt/repeat interactions.',
 'sources':{str(p.relative_to(ROOT)):sha(p) for p in [Path(__file__),HERE/'io_nonio_probe.c',HERE/'io_nonio_probe.v',HERE/'io_flags_candidate.py',HERE/'io_wait_candidate.py',HERE/'c_read_candidate.py',HERE/'c_read_half.h',HERE/'c_read_sampling.py',HERE/'c_read_half_test.c',HERE/'tv80_io_candidate.v',ROOT/'third_party/cpu/chips/z80.h',*sorted(vendor.glob('*.v'))]},
 'artifacts':{str(p.relative_to(out)):sha(p) for p in sorted(out.rglob('*')) if p.suffix in ('.txt','.v','.h')}}
 (out/'assessment.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps({k:v for k,v in report.items() if k in ('passed','cases')},indent=2))
 if not report['passed']:raise SystemExit(1)
if __name__=='__main__':main()
