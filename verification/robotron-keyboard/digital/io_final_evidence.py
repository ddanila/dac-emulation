#!/usr/bin/env python3
"""Retain/reassess complete I/O candidate results without claiming CPU completeness."""
import argparse,gzip,io,json,shutil,tarfile,tempfile
from pathlib import Path
from qualify import ROOT,sha
from io_boundary_evidence import artifacts,verify_capture
from verify_joint_phase import extract
from io_repeat_probe import expected as repeat_expected,vectors as repeat_vectors
from io_write_probe import programs as write_programs
from io_pin_review import compare
from pin_timing import rows
HERE=Path(__file__).resolve().parent
REPORTS=HERE/'reports/io-final'
RUNS={k:'keyboard-controller-'+v for k,v in {'write':'io-write','repeat':'io-repeat','pins':'io-pins','startup':'io-startup','instructions':'io-final-instructions','firmware':'io-final-firmware','wait':'io-final-read','nonio':'io-final-nonio'}.items()}

def verify(name,r,folder,base):
 if name in ('instructions','firmware','wait','nonio'):
  verify_capture(name,r,folder);return
 for p,d in r['sources'].items():assert sha(ROOT/p)==d,('source',p)
 for p,d in artifacts(name,r).items():assert sha(folder/p)==d,('artifact',p)
 if name=='write':
  intervals=[(1,2),(1,3),(1,4),(2,3),(2,4),(3,4),(3,5),(4,5),(4,6),(5,6),(1,8),(6,9)]
  assert [(x['instruction'],x['start'],x['stop']) for x in r['cases']]==[(name,a,b) for name in write_programs() for a,b in intervals]
  for row in r['cases']:
   sample=3
   while row['start']<=sample<row['stop']:sample+=2
   assert row['expectedWidth']==sample+2
   assert row['expectedData']==write_programs()[row['instruction']][1]
   for lang in ('c','hdl'):
    for profile in ('old','candidate'):
     path=folder/profile/(f"{row['instruction']}-{lang}-{row['start']}-{row['stop']}.txt")
     v={f[0]:int(f[1]) for l in path.read_text().splitlines() if (f:=l.split()) and f[0] in ('WIDTH','RELEASE','DATA','STABLE','HALT')}
     actual={'width':v.get('RELEASE',v.get('WIDTH')),'halt':v['HALT'],'data':v['DATA'],'stable':v['STABLE']}
     assert actual==row[profile+'-'+lang]
     if profile=='candidate':assert actual=={'width':sample+2,'halt':1,'data':row['expectedData'],'stable':1}
  assert r['passed'] and all(r['negativeControls'].values())
 elif name=='repeat':
  assert [(x['opcode'],x['b'],x['data'],x['registerC'],x['l'],x['pc']-12,x['mode']) for x in r['cases']]==list(repeat_vectors())
  for row in r['cases']:
   target=repeat_expected(row['opcode'],row['data'],row['b'],row['registerC'],row['l'],row['pc'])
   assert row['expected']==target
   for lang in ('c','hdl'):
    for profile in ('old','candidate'):
     path=folder/str(row['id'])/(profile+'-'+lang+'.txt')
     actual=[list(map(int,l.split()[1:])) for l in path.read_text().splitlines() if l.startswith('RESULT ')][0]
     assert row[profile+'-'+lang]==actual
     if profile=='candidate':assert actual==[target,0x42,1,1]
  assert r['passed'] and all(r['negativeControls'].values())
 elif name=='pins':
  assert [x['id'] for x in r['cases']]==['plain','write-wait','read-wait','reset-write','reset-read']
  for row in r['cases']:
   rebuilt=compare(rows(folder/(row['id']+'-c.txt')),rows(folder/(row['id']+'-hdl.txt')))
   assert all(row[k]==v for k,v in rebuilt.items()) and rebuilt['ioPinsAgree'] and rebuilt['ioHalfEdges']
  assert r['passed']
 elif name=='startup':
  for p,d in r['candidateSources'].items():assert sha(base/'firmware'/p)==d,p
  assert [x['initial'] for x in r['cases']]==[-1,0,1,2,3]
  reference=r['cases'][0]['hdl']['observableTrace']
  for row in r['cases']:
   for lang in ('c','hdl'):
    if lang=='c' and row['initial']<0:continue
    lines=(folder/f"{lang}-{row['initial']}.txt").read_text().splitlines()
    visible=[l for l in lines if l.startswith(('IO ','KNOWN ','BIT '))]
    assert visible==reference==row[lang]['observableTrace']
    assert [l for l in visible if l.startswith('KNOWN ')]==row[lang]['known'] and row[lang]['known']
  assert r['passed'] and not r['contract']['initialLedValidity']


def summary(reports):
 connectivity=HERE.parent/'reference/connectivity.json'
 components=json.loads(connectivity.read_text())['components']
 assert components['A5']['pins']['25']==components['X1']['pins']['A9']=='/BUSRQ_N'
 assert components['R6.5']['pins']=={'1':'/+5V','2':'/BUSRQ_N'}
 return {'qualified':False,'productionChanged':False,'boardControlSourceSha256':sha(connectivity),'gates':{
 'writeWaitAndRelease':reports['write']['passed'],'interruptedRepeatFlags':reports['repeat']['passed'],
 'ordinaryIoPinAgreement':reports['pins']['passed'],'startupLedValidity':reports['startup']['passed'],
 'readWaitHalfEdges':reports['wait']['passed'],'nonIoSameCoreRegression':reports['nonio']['passed'],
 'instructionDataAndFlags':reports['instructions']['allLateCasesAgree'],
 'firmwareFunctionalAgreement':reports['firmware']['functionalAgreement'],
 'serialCycleAgreement':reports['firmware']['serialCycleAgreement'],
 'knownLedTransitionAgreement':reports['firmware']['realLedTransitionAgreement'],
 'crossCoreArbitration':False,'allCpuPinsQualified':False,'productionAdopted':False},
 'boundary':'Explicit Z80 reference I/O candidate. Ordinary I/O pins agree at both labelled edges, including reset. Startup LEDs are invalid until A6 is clocked; arbitrary initial bits converge then. Non-I/O regression is same-core; memory/refresh/interrupt-acknowledge pins and C BUSRQ/BUSACK remain outside qualification. X1 A9 exposes BUSRQ, so full external board-control coverage is not claimed. U880 specimen fidelity and analog qualification remain separate.'}


def main():
 ap=argparse.ArgumentParser();ap.add_argument('--retain',action='store_true');a=ap.parse_args()
 if a.retain:
  REPORTS.mkdir(parents=True,exist_ok=True)
  reports={k:json.loads((ROOT/'build'/v/'assessment.json').read_text()) for k,v in RUNS.items()}
  with tempfile.TemporaryDirectory() as temp:
   stage=Path(temp)
   for name,r in reports.items():
    run=ROOT/'build'/RUNS[name]
    for p in artifacts(name,r):
     dest=stage/name/p;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(run/p,dest)
    # Startup also depends on the generated falling-edge wrapper.
    if name=='firmware':
     p='sampling/tv80n_falling.v';dest=stage/name/p;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(run/p,dest)
   for name,r in reports.items():
    verify(name,r,stage/name,stage)
    (REPORTS/(name+'.json')).write_text(json.dumps(r,indent=2)+'\n')
   with (REPORTS/'captures.tar.gz').open('wb') as f:
    with gzip.GzipFile(filename='',fileobj=f,mode='wb',mtime=0) as gz:
     with tarfile.open(fileobj=gz,mode='w') as tar:
      for p in sorted(stage.rglob('*')):
       if p.is_file():
        data=p.read_bytes();info=tarfile.TarInfo(str(p.relative_to(stage)));info.size=len(data);info.mode=0o644;tar.addfile(info,io.BytesIO(data))
  (REPORTS/'summary.json').write_text(json.dumps(summary(reports),indent=2)+'\n')
  (REPORTS/'receipt.json').write_text(json.dumps({'verifierSha256':sha(Path(__file__)),'files':{p.name:sha(p) for p in sorted(REPORTS.iterdir()) if p.is_file() and p.name!='receipt.json'}},indent=2)+'\n')
 receipt=json.loads((REPORTS/'receipt.json').read_text());assert receipt['verifierSha256']==sha(Path(__file__))
 for p,d in receipt['files'].items():assert sha(REPORTS/p)==d,p
 reports={name:json.loads((REPORTS/(name+'.json')).read_text()) for name in RUNS}
 with tempfile.TemporaryDirectory() as temp:
  stage=Path(temp);extract(REPORTS/'captures.tar.gz',stage)
  for name,r in reports.items():verify(name,r,stage/name,stage)
 assert json.loads((REPORTS/'summary.json').read_text())==summary(reports)
 print('Complete I/O candidate evidence verified; broader CPU pins and production remain explicit gates.')
if __name__=='__main__':main()
