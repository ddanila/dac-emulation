#!/usr/bin/env python3
"""Reproducible keyboard reference-board comparison. Differences are never a pass.
Default tests the common supported subset. --audit compares the full bus range;
--rom adds independent TV80 firmware execution. Both return nonzero on mismatch.
"""
import argparse,hashlib,json,re,subprocess,sys
from pathlib import Path
R=Path(__file__).resolve().parent;ROOT=R.parents[1];OUT=ROOT/'build/keyboard-controller'
def run(args,**kwargs):return subprocess.run([str(a) for a in args],cwd=ROOT,check=True,**kwargs)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--audit',action='store_true');p.add_argument('--rom',type=Path);p.add_argument('--wave',action='store_true');a=p.parse_args();OUT.mkdir(parents=True,exist_ok=True)
 run([sys.executable,R/'generate.py','--check'])
 report={'schema':1,'scope':'reference digital boundary; not specimen timing or complete analog simulation','connectivitySha256':sha(R/'reference/connectivity.json'),'sources':{str(f.relative_to(ROOT)):sha(f) for f in sorted(list(R.glob('*.*'))+list((R/'generated').glob('*.v'))) if f.suffix in ['.py','.c','.v']},'productionKeyboardSha256':sha(ROOT/'machines/robotron1715m/keyboard.c'),'productionKeyboardHeaderSha256':sha(ROOT/'machines/robotron1715m/keyboard.h'),'cpuSources':{p:sha(ROOT/p) for p in ['common/cpu/z80.c','common/cpu/z80.h','third_party/cpu/chips/z80.h']}}
 run(['iverilog','-g2012','-s','service_tb','-o',OUT/'service.vvp',R/'chips.v',R/'generated/controller.v',R/'service_tb.v'])
 service=subprocess.run(['vvp',str(OUT/'service.vvp')],cwd=ROOT,text=True,capture_output=True,timeout=30)
 (OUT/'service.log').write_text(service.stdout+service.stderr)
 sm=re.search(r'SERVICE checks=(\d+) mismatches=(\d+)',service.stdout)
 if service.returncode or not sm:raise RuntimeError(service.stdout+service.stderr)
 report['service']={'checks':int(sm[1]),'mismatches':int(sm[2]),'equivalent':True,'scope':'BR1/BR2 digital isolation, external injection, floating reset, clock pullup and conflicting drivers; analog sources are boundaries.'}
 run(['cc','-std=c11','-O2','-Wall','-Wextra','-Werror',R/'bus_probe.c','machines/robotron1715m/keyboard.c','common/cpu/z80.c','-o',OUT/'bus-probe'])
 with (OUT/'bus.txt').open('w') as f:run([OUT/'bus-probe']+([] if a.audit else ['smoke']),stdout=f)
 run(['iverilog','-g2012','-s','bus_tb','-o',OUT/'bus.vvp',R/'chips.v',R/'generated/controller.v',R/'bus_tb.v'])
 args=['vvp',str(OUT/'bus.vvp'),'+vectors='+str(OUT/'bus.txt')]
 if a.wave:args+=['+wave='+str(OUT/'bus.vcd')]
 result=subprocess.run(args,cwd=ROOT,text=True,capture_output=True,timeout=30);(OUT/'bus.log').write_text(result.stdout+result.stderr)
 m=re.search(r'BUS vectors=(\d+) mismatches=(\d+)',result.stdout)
 if not m:raise RuntimeError(result.stdout+result.stderr)
 report['bus']={'mode':'full-address-audit' if a.audit else 'one-column-and-low-output-range','vectors':int(m[1]),'mismatches':int(m[2]),'equivalent':result.returncode==0,'firstDifferences':[line for line in result.stdout.splitlines() if line.startswith('DIFF')]}
 if a.rom:
  rom=a.rom.resolve();data=rom.read_bytes()
  if len(data)!=2048:raise ValueError('Expected a 2048-byte keyboard ROM')
  source=json.loads((ROOT/'third_party/cpu/tv80/SOURCE.json').read_text())
  for name,digest in source['files'].items():
   if sha(ROOT/'third_party/cpu/tv80'/name)!=digest:raise ValueError('TV80 source differs: '+name)
  (OUT/'rom.hex').write_text('\n'.join(f'{v:02x}' for v in data)+'\n')
  run(['cc','-std=c11','-O2','-Wall','-Wextra','-Werror',R/'firmware_probe.c','machines/robotron1715m/keyboard.c','common/cpu/z80.c','-o',OUT/'firmware-probe'])
  with (OUT/'firmware-c.txt').open('w') as f:run([OUT/'firmware-probe',rom],stdout=f)
  run(['iverilog','-g2012','-s','firmware_tb','-o',OUT/'firmware.vvp',*sorted((ROOT/'third_party/cpu/tv80').glob('*.v')),R/'chips.v',R/'generated/controller.v',R/'firmware_tb.v'])
  args=['vvp',OUT/'firmware.vvp','+rom='+str(OUT/'rom.hex')]
  if a.wave:args+=['+wave='+str(OUT/'firmware.vcd')]
  with (OUT/'firmware-hdl.txt').open('w') as f:run(args,stdout=f,timeout=300)
  parsed=[]
  for lang in ['c','hdl']:
   lines=(OUT/f'firmware-{lang}.txt').read_text().splitlines()
   parsed.append({kind:[(int(l.split()[1]),l.split()[2]) for l in lines if l.startswith(kind+' ')] for kind in ['BIT','LED','EDGE']})
  c,h=parsed;bits_c=[v for _,v in c['BIT']];bits_h=[v for _,v in h['BIT']]
  first=next((i for i,(x,y) in enumerate(zip(bits_c,bits_h)) if x!=y),None)
  if first is None and len(bits_c)!=len(bits_h):first=min(len(bits_c),len(bits_h))
  differences=[{'cycle':x[0],'c':x[1],'hdl':y[1]} for x,y in zip(c['LED'],h['LED']) if x!=y]
  count=lambda lo,hi:sum(lo<=t<hi for t,_ in c['BIT'])
  coverage={'normal':count(200000,400000),'shift':count(800000,1000000),'ctrl':count(1800000,2000000),'repeat':count(2400000,3800000),'afterRepeatRelease':count(4000000,4200000),'afterReset':count(4400000,4600000)}
  coverage_pass=all(coverage[k]>=26 for k in ['normal','shift','ctrl','afterReset']) and coverage['repeat']>=52 and coverage['afterRepeatRelease']==0
  report['firmware']={'romSha256':sha(rom),'cpu':source,'cycles':4600000,'stimulusCoverage':coverage,'stimulusCoveragePassed':coverage_pass,'cBits':len(bits_c),'hdlBits':len(bits_h),'serialSequenceEquivalent':bool(bits_c) and bits_c==bits_h,'firstSerialDifference':first,'ledDifferences':differences,'cLedEdges':len(c['EDGE']),'hdlLedEdges':len(h['EDGE']),'ledTransitionsEquivalent':[v for _,v in c['EDGE']]==[v for _,v in h['EDGE']], 'serialCycleOffsets':sorted(set(y[0]-x[0] for x,y in zip(c['BIT'],h['BIT']))),'ledCycleOffsetCounts':{str(offset):sum(y[0]-x[0]==offset for x,y in zip(c['EDGE'],h['EDGE'])) for offset in sorted(set(y[0]-x[0] for x,y in zip(c['EDGE'],h['EDGE'])))},'cycleEquivalent':False,'cLedSamples':c['LED'],'hdlLedSamples':h['LED'],'timing':'Cycles recorded; ordinal bit comparison allows CPU timing differences and is not cycle equivalence.','equivalent':coverage_pass and bool(bits_c) and bits_c==bits_h and c['LED']==h['LED'] and [v for _,v in c['EDGE']]==[v for _,v in h['EDGE']]}
 report['equivalent']=report['bus']['equivalent'] and report.get('firmware',{'equivalent':True})['equivalent']
 (OUT/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k not in ['sources']},indent=2))
 return 0 if report['equivalent'] else 1
if __name__=='__main__':sys.exit(main())
