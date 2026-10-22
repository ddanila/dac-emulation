#!/usr/bin/env python3
"""Retain and verify C read-candidate evidence without closing unsupported gates."""
import argparse,gzip,io,json,tarfile,tempfile,subprocess
from pathlib import Path
from qualify import ROOT,sha,parse,assess
from review import observation_window
from verify_joint_phase import extract
from c_read_instructions import parse as instruction_parse
HERE=Path(__file__).resolve().parent
DEST=HERE/'reports/c-read'
BUILD={
 'instructions':ROOT/'build/keyboard-controller-c-read-instructions',
 'sampling':ROOT/'build/keyboard-controller-c-read-sampling',
 'assertion':ROOT/'build/keyboard-controller-c-read',
 'pair':ROOT/'build/keyboard-controller-c-read-pair-final',
}
def summary(reports):
 p=reports['pair'];i=reports['instructions']
 return {'qualified':False,'productionChanged':False,
  'gates':{'firmwareFunctionalAgreement':p['functionalAgreement'],'serialCycleAgreement':p['serialCycleAgreement'],'knownLedTransitionAgreement':p['realLedTransitionAgreement'],'lateInputDataAgreement':i['allLateDataAgree'],'fullInstructionIncludingFlagsAgreement':i['allLateCasesAgree'],'rawCycleAgreement':p['rawCycleAgreement'],'nonIoInterruptAndArbitrationQualified':False,'waitTransitionPhaseQualified':False},
  'boundary':'C address/control and explicit falling-edge I/O sampling candidates, paired with the HDL I/O boundary. Stable WAIT extension is tested; half-cycle WAIT transition acceptance, non-I/O pins, interrupts and arbitration are not qualified. Initial LED observations remain unequal and raw BUS logging uses different observation phases. Flag disagreement is retained, not resolved by choosing one core as the oracle.',
  'contractSha256':sha(HERE/'io-read-contract.json')}

def retain():
 DEST.mkdir(parents=True,exist_ok=True);reports={};files={}
 for kind,folder in BUILD.items():
  r=json.loads((folder/'assessment.json').read_text());reports[kind]=r
  for name,digest in r.get('sources',{}).items():
   if sha(ROOT/name)!=digest:raise ValueError('Producer changed '+name)
  (DEST/(kind+'.json')).write_bytes((folder/'assessment.json').read_bytes())
  artifacts=dict(r.get('artifacts',{}))
  for case in r.get('cases',[]):
   if 'scenario' in case:
    for name,digest in case['artifacts'].items():artifacts[case['scenario']['id']+'/'+name]=digest
  artifacts.update(r.get('generatedSources',{}))
  if kind=='assertion':artifacts['shadow/third_party/cpu/chips/z80.h']=r['candidateHeaderSha256']
  for name,digest in artifacts.items():
   path=folder/name
   if sha(path)!=digest:raise ValueError('Artifact changed '+str(path))
   files[kind+'/'+name]=path
 # Preserve the concrete snapshot-phase counterexample and its executable sources.
 negative=ROOT/'build/keyboard-controller-c-read-pair/column-08'
 control={}
 for name in ('probe.c','bench.v','c.txt','hdl.txt'):
  files['observation-control/'+name]=negative/name;control[name]=sha(negative/name)
 (DEST/'observation-control.json').write_text(json.dumps({'artifacts':control,'boundary':'Prior fixture samples HDL LED state at the start of a cycle and C after executing it. Compare against identical edge traces; do not change their timestamps.'},indent=2)+'\n')
 with (DEST/'captures.tar.gz').open('wb') as raw:
  with gzip.GzipFile(fileobj=raw,mode='wb',filename='',mtime=0) as zipped:
   with tarfile.open(fileobj=zipped,mode='w') as tar:
    for name,path in sorted(files.items()):
     data=path.read_bytes();member=tarfile.TarInfo(name);member.size=len(data);member.mode=0o644;tar.addfile(member,io.BytesIO(data))
 (DEST/'summary.json').write_text(json.dumps(summary(reports),indent=2)+'\n')
 names=[k+'.json' for k in BUILD]+['summary.json','observation-control.json','captures.tar.gz']
 (DEST/'receipt.json').write_text(json.dumps({n:sha(DEST/n) for n in names},indent=2)+'\n')

def verify():
 receipt=json.loads((DEST/'receipt.json').read_text())
 for name,digest in receipt.items():
  if sha(DEST/name)!=digest:raise ValueError('Retained evidence changed '+name)
 reports={k:json.loads((DEST/(k+'.json')).read_text()) for k in BUILD}
 for r in reports.values():
  for name,digest in r['sources'].items():
   if sha(ROOT/name)!=digest:raise ValueError('Producer source changed '+name)
  if r['qualified']:raise ValueError('Unsupported qualification claim')
 if summary(reports)!=json.loads((DEST/'summary.json').read_text()):raise ValueError('Summary changed')
 with tempfile.TemporaryDirectory() as temp:
  root=Path(temp).resolve();extract(DEST/'captures.tar.gz',root)
  joint=root/'joint';extract(HERE/'reports/joint-phase/captures.tar.gz',joint)
  for kind,r in reports.items():
   artifacts=dict(r.get('artifacts',{}));artifacts.update(r.get('generatedSources',{}))
   for name,digest in artifacts.items():
    if sha(root/kind/name)!=digest:raise ValueError('Captured artifact changed '+name)
  for kind in ('assertion','pair'):
   report=reports[kind]
   for kept in report['cases']:
    spec=kept['scenario'];folder=root/kind/spec['id']
    for name,digest in kept['artifacts'].items():
     if sha(folder/name)!=digest:raise ValueError('Case changed '+name)
    hpath=folder/'hdl.txt' if kind=='pair' else (HERE/'reports/joint-repeat/hdl.txt' if spec['id']=='baseline-repeat-release-reset' else joint/spec['id']/'hdl.txt')
    if kind=='assertion' and sha(hpath)!=kept['hdlSha256']:raise ValueError('HDL reference changed')
    c,co=observation_window(parse(folder/'c.txt'),spec['cycles']);h,ho=observation_window(parse(hpath),spec['cycles'])
    expected=assess(spec,c,h)
    for key,value in expected.items():
     if kept[key]!=value:raise ValueError('Comparison changed '+spec['id']+' '+key)
    if kept['realLedTransitionsEquivalent']!=(c['EDGE'][1:]==h['EDGE'][1:]):raise ValueError('LED transition claim changed')
    if kept['initialLedObservations']!={'c':c['EDGE'][:1],'hdl':h['EDGE'][:1]}:raise ValueError('Initial state hidden')
    if kept['outsideObservationInterval']!={'c':co,'hdl':ho}:raise ValueError('Observation boundary changed')
   for key,value in [('functionalAgreement',all(r['functionalAgreement'] for r in report['cases'])),('serialCycleAgreement',all(r['events']['BIT']['rawCycleEquivalent'] for r in report['cases'])),('realLedTransitionAgreement',all(r['realLedTransitionsEquivalent'] for r in report['cases']))]:
    if report[key]!=value:raise ValueError('Summary mismatch '+key)
  # The physical 8282 is transparent during active strobe. A changing matrix
  # must reach the input callback even if the same read remains selected.
  for label,source,expected in [('candidate',root/'pair/shadow',2),('production',ROOT,1)]:
   code=root/(label+'-matrix.c')
   code.write_text('#include '+json.dumps(str(source/'machines/robotron1715m/keyboard.h'))+'\n#include <assert.h>\nint main(void){unsigned char rom[2048]={0};robotron_keyboard k;robotron_keyboard_init(&k,rom,0,0);k.matrix[0]=1;assert(k.cpu.bus.input(&k,0x8001)==1);k.cpu.pins=Z80_IORQ|Z80_RD;k.matrix[0]=2;assert(k.cpu.bus.input(&k,0x8001)=='+str(expected)+');return 0;}\n')
   exe=root/(label+'-matrix')
   subprocess.run(['cc','-std=c11','-O2','-Wall','-Wextra','-Werror',str(code),str(source/'machines/robotron1715m/keyboard.c'),str(source/'common/cpu/z80.c'),'-o',str(exe)],check=True)
   subprocess.run([str(exe)],check=True)
  r=reports['instructions'];late=[]
  for case in r['lateCases']:
   folder=root/'instructions'/case['id'];c=instruction_parse(folder/'half.txt');h=instruction_parse(folder/'hdl.txt')
   data=c['RAM']==h['RAM'] and [e[1:] for e in c['OUT']]==[e[1:] for e in h['OUT']] and c['FINAL'][-1][0]==h['AF'][-1][0]
   flags=c['FINAL'][-1][1]==h['AF'][-1][1]
   if (case['dataAgreement'],case['flagsAgreement'],case['agreement'])!=(data,flags,data and flags):raise ValueError('Instruction flags/data claim changed')
   late.append((data,flags))
  if r['allLateDataAgree']!=all(d for d,f in late) or r['allLateCasesAgree']!=all(d and f for d,f in late):raise ValueError('Late-input gate changed')
  negative=root/'observation-control';control=json.loads((DEST/'observation-control.json').read_text())
  for name,digest in control['artifacts'].items():
   if sha(negative/name)!=digest:raise ValueError('Observation control changed')
  c,h=[observation_window(parse(negative/(lang+'.txt')),1900000)[0] for lang in ('c','hdl')]
  if c['EDGE']!=h['EDGE'] and c['EDGE'][1:]!=h['EDGE'][1:]:raise ValueError('Control edges no longer agree')
  if c['LED']==h['LED']:raise ValueError('Observation negative control no longer fails')
 print('Read candidates, firmware comparisons and retained counterexamples verified; promotion remains gated.')

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--retain',action='store_true');a=p.parse_args()
 if a.retain:retain()
 verify()
