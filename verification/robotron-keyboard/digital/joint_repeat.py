#!/usr/bin/env python3
"""Exercise the unchanged long repeat/release/reset fixture through the I/O adapter."""
import argparse,json,subprocess
from pathlib import Path
from qualify import ROOT,BOARD,sha,parse,assess
from review import observation_window
HERE=Path(__file__).resolve().parent

def evaluate(out):
 values=[observation_window(parse(out/name),4600000)[0] for name in ('c.txt','hdl.txt')]
 r=assess({'id':'baseline-repeat-release-reset','cycles':4600000,'events':[]},*values)
 r['coverage']={}
 for name,v in zip(('c','hdl'),values):
  count=lambda lo,hi:sum(lo<=int(e[0])<hi for e in v['BIT'])
  r['coverage'][name]={'repeat':count(2400000,3800000),'afterRelease':count(4000000,4200000),'afterReset':count(4400000,4600000)}
 r['coveragePassed']=all(v['repeat']>=52 and v['afterRelease']==0 and v['afterReset']>=26 for v in r['coverage'].values())
 return r

def main():
 p=argparse.ArgumentParser();p.add_argument('--rom',type=Path);p.add_argument('--out',type=Path,default=ROOT/'build/keyboard-controller-joint-repeat');p.add_argument('--verify',type=Path);a=p.parse_args()
 if a.verify:
  r=json.loads((a.verify/'assessment.json').read_text())
  for name,digest in r['sources'].items():
   if sha(ROOT/name)!=digest:raise ValueError('Changed source '+name)
  for name,digest in r['artifacts'].items():
   if sha(a.verify/name)!=digest:raise ValueError('Changed artifact '+name)
  if evaluate(a.verify)!=r['comparison'] or r['qualified']:raise ValueError('Changed assessment')
  print('Retained candidate repeat/release/reset comparison verified.');return
 if a.rom is None:p.error('--rom required')
 out=a.out.resolve();out.mkdir(parents=True,exist_ok=True);rom=a.rom.resolve()
 expected=json.loads((BOARD/'reports/full-audit.json').read_text())['firmware']['romSha256']
 if sha(rom)!=expected:raise ValueError('Unexpected reference ROM')
 (out/'rom.hex').write_text('\n'.join(f'{x:02x}' for x in rom.read_bytes())+'\n')
 text=(BOARD/'firmware_tb.v').read_text();needle='tv80n cpu('
 if text.count(needle)!=1:raise ValueError('CPU template changed')
 (out/'bench.v').write_text(text.replace(needle,'tv80_io_candidate cpu('))
 rtl=[*sorted((ROOT/'third_party/cpu/tv80').glob('*.v')),HERE/'tv80_io_candidate.v',BOARD/'chips.v',BOARD/'generated/controller.v']
 c=[BOARD/'firmware_probe.c',ROOT/'machines/robotron1715m/keyboard.c',ROOT/'common/cpu/z80.c']
 def run(args,log=None):
  if log:
   with (out/log).open('w') as f:subprocess.run(list(map(str,args)),check=True,stdout=f,timeout=600)
  else:subprocess.run(list(map(str,args)),check=True,timeout=30)
 run(['cc','-std=c11','-O2','-Wall','-Wextra','-Werror',*c,'-o',out/'probe'])
 run([out/'probe',rom],'c.txt')
 run(['iverilog','-g2012','-s','firmware_tb','-o',out/'bench.vvp',*rtl,out/'bench.v'])
 run(['vvp',out/'bench.vvp','+rom='+str(out/'rom.hex')],'hdl.txt')
 r=evaluate(out)
 sources=[Path(__file__),HERE/'qualify.py',HERE/'review.py',BOARD/'firmware_tb.v',*rtl,*c,ROOT/'common/cpu/z80.h',ROOT/'machines/robotron1715m/keyboard.h',ROOT/'third_party/cpu/chips/z80.h']
 report={'qualified':False,'romSha256':sha(rom),'comparison':r,'sources':{str(p.relative_to(ROOT)):sha(p) for p in sources},'artifacts':{name:sha(out/name) for name in ('bench.v','c.txt','hdl.txt')},'boundary':'Unchanged standard held-repeat/release/reset stimulus with the experimental adapter; exact CPU pin phases and electrical timing remain unqualified.'}
 (out/'assessment.json').write_text(json.dumps(report,indent=2)+'\n')
 print(r['functionalAgreement'],r['events']['BIT']['rawCycleEquivalent'],r['coveragePassed'])
 if not r['functionalAgreement'] or not r['events']['BIT']['rawCycleEquivalent'] or not r['coveragePassed']:raise SystemExit(1)
if __name__=='__main__':main()
