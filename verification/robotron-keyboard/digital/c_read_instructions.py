#!/usr/bin/env python3
"""Instruction and negative sampling witnesses for the isolated read candidate."""
import argparse,json,subprocess
from pathlib import Path
from qualify import ROOT,sha
from c_read_candidate import generate
HERE=Path(__file__).resolve().parent

def programs():
 p={'immediate':bytes.fromhex('3e a5 db 80 d3 81 76'),
    'dd-prefix-in':bytes.fromhex('3e a5 dd db 80 d3 81 76'),
    'fd-prefix-in':bytes.fromhex('3e a5 fd db 80 d3 81 76'),
    'indexed-memory':bytes.fromhex('dd 21 00 80 dd 36 01 5a dd 7e 01 d3 81 76')}
 for reg,op,move in [('b',0x40,0x78),('c',0x48,0x79),('d',0x50,0x7a),('e',0x58,0x7b),('h',0x60,0x7c),('l',0x68,0x7d),('flags',0x70,0x7f),('a',0x78,0x7f)]:
  p['in-'+reg]=bytes([0x01,0x80,0xa5,0xed,op,move,0xd3,0x81,0x76])
 for name,op in [('ini',0xa2),('ind',0xaa),('inir',0xb2),('indr',0xba),('outi',0xa3),('outd',0xab),('otir',0xb3),('otdr',0xbb)]:
  p[name]=bytes.fromhex('21 01 80 36 69 2b 36 96 01 80 02')+bytes([0xed,op,0x76])
 return p

def parse(path):
 r={k:[] for k in ('OUT','MEM','RAM','READ','FINAL','LATE','HALT','AF')}
 for line in path.read_text().splitlines():
  f=line.split()
  if f and f[0] in r:r[f[0]].append([int(x) for x in f[1:]])
 return r

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,default=ROOT/'build/keyboard-controller-c-read-instructions');a=ap.parse_args();out=a.out.resolve();out.mkdir(parents=True,exist_ok=True)
 (out/'candidate.h').write_text(generate((ROOT/'third_party/cpu/chips/z80.h').read_text()))
 def run(args,log=None):
  if log:
   with log.open('w') as f:subprocess.run(list(map(str,args)),check=True,stdout=f,timeout=30)
  else:subprocess.run(list(map(str,args)),check=True,timeout=30)
 run(['cc','-std=c11','-O2','-Wall','-Wextra','-Werror','-I',out,HERE/'c_read_instructions.c','-o',out/'probe'])
 half=(HERE/'c_read_instructions.c').read_text().replace('#include "candidate.h"','#include "c_read_half.h"')
 half=half.replace('z80_t cpu;uint64_t p=z80_init(&cpu);','c_read_half model;c_read_reset(&model);uint64_t p=model.pins;')
 half=half.replace('cpu.step','model.cpu.step').replace('p=z80_tick(&cpu,p);','p=c_read_rise(&model,p);').replace('p=z80_reset(&cpu);','c_read_reset(&model);p=model.pins;')
 half=half.replace('  previous_read=read;previous_write=write;','  previous_read=read;previous_write=write;\n  p=c_read_fall(&model,p);')
 for field in ('a','f','bc','hl'):half=half.replace('cpu.'+field,'model.cpu.'+field)
 (out/'half.c').write_text(half)
 run(['cc','-std=c11','-O2','-Wall','-Wextra','-Werror','-I',out,'-I',HERE,out/'half.c','-o',out/'half'])
 rtl=[*sorted((ROOT/'third_party/cpu/tv80').glob('*.v')),HERE/'tv80_io_candidate.v',HERE/'c_read_instructions.v']
 run(['iverilog','-g2012','-s','c_read_instructions','-o',out/'probe.vvp',*rtl])
 results=[]
 for name,program in programs().items():
  for mode,reset in ((0,0),(1,0),(0,1)):
   folder=out/f'{name}-{mode}-{reset}';folder.mkdir(exist_ok=True)
   (folder/'program.bin').write_bytes(program);(folder/'program.hex').write_text('\n'.join(f'{x:02x}' for x in program)+'\n')
   run([out/'probe',folder/'program.bin',mode,reset,0],folder/'c.txt')
   run(['vvp',out/'probe.vvp','+rom='+str(folder/'program.hex'),f'+mode={mode}',f'+reset={reset}'],folder/'hdl.txt')
   run([out/'half',folder/'program.bin',mode,reset,0],folder/'half.txt')
   c,h=[parse(folder/f'{lang}.txt') for lang in ('c','hdl')]
   half=parse(folder/'half.txt')
   half_passed=half['RAM']==h['RAM'] and [e[1:] for e in half['OUT']]==[e[1:] for e in h['OUT']] and half['FINAL'][-1][-1]==1
   passed=c['RAM']==h['RAM'] and [e[1:] for e in c['OUT']]==[e[1:] for e in h['OUT']] and c['FINAL'][-1][-1]==1 and h['HALT']==[[1]]
   # Stable address throughout each selected read, including external wait ticks.
   bursts=[]
   for e in c['READ']:
    if not bursts or e[0]!=bursts[-1][-1][0]+1:bursts.append([])
    bursts[-1].append(e)
   stable=all(len({e[1] for e in b})==1 for b in bursts)
   r={'id':folder.name,'functionalAgreement':passed,'halfCycleFunctionalAgreement':half_passed,'stableReadAddress':stable,'waitReadTicks':sum(e[3] for e in c['READ']),'cOutputs':c['OUT'],'hdlOutputs':h['OUT'],'ramEquivalent':c['RAM']==h['RAM']}
   results.append(r)
 # Changing data in T3 must work for each input instruction family, not only IN A.
 run(['python3',HERE/'c_read_sampling.py','--out',out/'sampling'])
 falling=[p for p in rtl if p.name!='tv80n.v']+[out/'sampling/tv80n_falling.v']
 run(['iverilog','-g2012','-s','c_read_instructions','-Pc_read_instructions.LATE=1','-o',out/'falling.vvp',*falling])
 late_cases=[]
 for name,program in programs().items():
  if name=='indexed-memory' or name.startswith(('out','ot')):continue
  for mode,reset in ((0,0),(1,0),(0,1)):
   folder=out/f'late-{name}-{mode}-{reset}';folder.mkdir(exist_ok=True)
   (folder/'program.bin').write_bytes(program);(folder/'program.hex').write_text('\n'.join(f'{x:02x}' for x in program)+'\n')
   run([out/'half',folder/'program.bin',mode,reset,1],folder/'half.txt')
   run(['vvp',out/'falling.vvp','+rom='+str(folder/'program.hex'),f'+mode={mode}',f'+reset={reset}'],folder/'hdl.txt')
   c,h=parse(folder/'half.txt'),parse(folder/'hdl.txt')
   passed=c['RAM']==h['RAM'] and [e[1:] for e in c['OUT']]==[e[1:] for e in h['OUT']] and c['FINAL'][-1][:2]==h['AF'][-1]
   late_cases.append({'id':folder.name,'agreement':passed,'dataAgreement':c['RAM']==h['RAM'] and [e[1:] for e in c['OUT']]==[e[1:] for e in h['OUT']] and c['FINAL'][-1][0]==h['AF'][-1][0],'flagsAgreement':c['FINAL'][-1][1]==h['AF'][-1][1],'cAF':c['FINAL'][-1][:2],'hdlAF':h['AF'][-1],'lateSamples':len(c['LATE'])})
 # A counterexample to claiming half-cycle qualification from constant inputs.
 folder=out/'late';folder.mkdir(exist_ok=True);(folder/'program.bin').write_bytes(programs()['immediate'])
 run([out/'probe',folder/'program.bin',0,0,1],folder/'c.txt');late=parse(folder/'c.txt')
 run([out/'half',folder/'program.bin',0,0,1],folder/'half.txt');half_late=parse(folder/'half.txt')
 report={'qualified':False,'cases':results,'lateCases':late_cases,'allLateCasesAgree':all(r['agreement'] and r['lateSamples'] for r in late_cases),'allLateDataAgree':all(r['dataAgreement'] and r['lateSamples'] for r in late_cases),'functionalAgreement':all(r['functionalAgreement'] and r['halfCycleFunctionalAgreement'] and r['stableReadAddress'] for r in results),'lateSampling':{'halfCycleLaterValueUsed':half_late['OUT'][-1][-1]==0x34,'halfCycleOutputs':half_late['OUT'],'laterValue':0x34,'observedOutputs':late['OUT'],'changeWitnesses':late['LATE'],'laterValueUsed':bool(late['OUT']) and late['OUT'][-1][-1]==0x34},'sources':{str(p.relative_to(ROOT)):sha(p) for p in [Path(__file__),HERE/'c_read_candidate.py',HERE/'c_read_instructions.c',HERE/'c_read_half.h',HERE/'c_read_sampling.py',HERE/'c_read_half_test.c',ROOT/'third_party/cpu/chips/z80.h',*rtl]},'artifacts':{str(p.relative_to(out)):sha(p) for p in sorted(out.rglob('*')) if p.is_file() and p.suffix in ('.txt','.hex','.bin','.h','.c')},'boundary':'DD/FD before IN are ignored prefixes, not an indexed I/O addressing mode. Indexed memory is a separate control. Constant-input instruction agreement does not qualify T3 falling-edge sampling; the late-input witness deliberately exposes that limitation.'}
 (out/'assessment.json').write_text(json.dumps(report,indent=2)+'\n')
 print('Functional:',report['functionalAgreement'],'late data used:',report['lateSampling']['laterValueUsed'])
 for r in results:
  if not r['functionalAgreement']:print(r)
 print('Late instruction agreement:',report['allLateCasesAgree'])
 print('Flag disagreements:',sum(not r['flagsAgreement'] for r in late_cases))
 if not report['functionalAgreement'] or not report['allLateDataAgree'] or not report['lateSampling']['halfCycleLaterValueUsed'] or report['lateSampling']['laterValueUsed']:raise SystemExit(1)
if __name__=='__main__':main()
