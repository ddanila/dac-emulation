#!/usr/bin/env python3
"""Compare an isolated C read candidate with retained joint-boundary HDL captures."""
import argparse,json,shutil,subprocess
from pathlib import Path
from qualify import ROOT,BOARD,sha,parse,assess,scenarios
from review import observation_window
from c_read_candidate import generate
HERE=Path(__file__).resolve().parent

def shadow(out):
 files=['common/cpu/z80.c','common/cpu/z80.h','machines/robotron1715m/keyboard.c','machines/robotron1715m/keyboard.h']
 for name in files:
  p=out/name;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,p)
 header=out/'third_party/cpu/chips/z80.h';header.parent.mkdir(parents=True,exist_ok=True)
 header.write_text(generate((ROOT/'third_party/cpu/chips/z80.h').read_text()))
 return files

def main():
 p=argparse.ArgumentParser();p.add_argument('--rom',type=Path,required=True);p.add_argument('--out',type=Path,default=ROOT/'build/keyboard-controller-c-read');a=p.parse_args();out=a.out.resolve();out.mkdir(parents=True,exist_ok=True)
 copies=shadow(out/'shadow');rom=a.rom.resolve();parent=HERE/'reports/joint-phase';retained=json.loads((parent/'assessment.json').read_text())
 if sha(rom)!=retained['romSha256']:raise ValueError('ROM changed')
 from verify_joint_phase import extract
 extract(parent/'captures.tar.gz',out/'hdl')
 baseline=out/'baseline';extract(HERE/'reports/captures.tar.gz',baseline)
 results=[]
 for spec in scenarios()+[{'id':'baseline-repeat-release-reset','cycles':4600000,'events':[]}]:
  dest=out/spec['id'];dest.mkdir(exist_ok=True)
  if spec['id']=='baseline-repeat-release-reset':
   c=(BOARD/'firmware_probe.c').read_text().replace('../../machines/robotron1715m/keyboard.h',str(out/'shadow/machines/robotron1715m/keyboard.h'))
   hpath=HERE/'reports/joint-repeat/hdl.txt'
  else:
   c=(baseline/spec['id']/'probe.c').read_text().replace(str(ROOT/'machines/robotron1715m/keyboard.h'),str(out/'shadow/machines/robotron1715m/keyboard.h'))
   hpath=out/'hdl'/spec['id']/'hdl.txt'
  (dest/'probe.c').write_text(c)
  subprocess.run(['cc','-std=c11','-O2','-Wall','-Wextra','-Werror',str(dest/'probe.c'),str(out/'shadow/machines/robotron1715m/keyboard.c'),str(out/'shadow/common/cpu/z80.c'),'-o',str(dest/'probe')],check=True)
  with (dest/'c.txt').open('w') as f:subprocess.run([str(dest/'probe'),str(rom)],check=True,stdout=f,timeout=120)
  cv,co=observation_window(parse(dest/'c.txt'),spec['cycles']);hv,ho=observation_window(parse(hpath),spec['cycles'])
  r=assess(spec,cv,hv);r['outsideObservationInterval']={'c':co,'hdl':ho}
  r['realLedTransitionsEquivalent']=cv['EDGE'][1:]==hv['EDGE'][1:]
  r['initialLedObservations']={'c':cv['EDGE'][:1],'hdl':hv['EDGE'][:1]}
  r['artifacts']={'c.txt':sha(dest/'c.txt'),'probe.c':sha(dest/'probe.c')};r['hdlSha256']=sha(hpath)
  # The initial C value is an initialization observation, never deleted from raw comparison.
  results.append(r);print(spec['id'],r['functionalAgreement'],r['events']['BIT']['rawCycleEquivalent'],r['realLedTransitionsEquivalent'],flush=True)
 sources=[Path(__file__),HERE/'c_read_candidate.py',HERE/'qualify.py',HERE/'review.py',ROOT/'third_party/cpu/chips/z80.h',BOARD/'firmware_probe.c',*(ROOT/f for f in copies)]
 report={'qualified':False,'productionChanged':False,'romSha256':sha(rom),'sources':{str(p.relative_to(ROOT)):sha(p) for p in sources},'candidateHeaderSha256':sha(out/'shadow/third_party/cpu/chips/z80.h'),'hdlAssessmentSha256':sha(parent/'assessment.json'),'repeatAssessmentSha256':sha(HERE/'reports/joint-repeat/assessment.json'),'cases':results,'functionalAgreement':all(r['functionalAgreement'] for r in results),'serialCycleAgreement':all(r['events']['BIT']['rawCycleEquivalent'] for r in results),'realLedTransitionAgreement':all(r['realLedTransitionsEquivalent'] for r in results),'boundary':'Whole-cycle read assertion candidate, not a half-cycle input-sampling model. Initial LED observations and raw BUS differences remain visible. No production or vendored files are modified.'}
 (out/'assessment.json').write_text(json.dumps(report,indent=2)+'\n')
if __name__=='__main__':main()
