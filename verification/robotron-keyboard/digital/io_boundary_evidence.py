#!/usr/bin/env python3
"""Retain and independently reassess scoped I/O promotion evidence."""
import argparse,gzip,io,json,shutil,tarfile,tempfile
from pathlib import Path
from qualify import ROOT,sha,parse as firmware_parse,assess,scenarios
from review import observation_window
from c_read_instructions import parse
from io_flags_probe import expected,vectors
from verify_joint_phase import extract

HERE=Path(__file__).resolve().parent
REPORTS=HERE/'reports/io-boundary'
RUNS={
 'flags':'keyboard-controller-io-flags',
 'wait':'keyboard-controller-io-wait',
 'nonio':'keyboard-controller-io-nonio',
 'instructions':'keyboard-controller-io-boundary-instructions',
 'firmware':'keyboard-controller-io-boundary-firmware',
}

def artifacts(name,r):
 files=dict(r.get('artifacts',{}))
 files.update(r.get('generatedSources',{}))
 files.update(r.get('composedArtifacts',{}))
 if name=='firmware':
  for case in r['cases']:
   files.update({case['scenario']['id']+'/'+p:d for p,d in case['artifacts'].items()})
 return files


def verdict(reports):
 return {'qualified':False,'productionChanged':False,'gates':{
  'normalCompletionIoFlags':reports['flags']['cPass'] and reports['flags']['candidatePass'] and reports['instructions']['allLateCasesAgree'],
  'readWaitHalfEdgeAcceptance':reports['wait']['passed'],
  'nonIoSameCoreRegression':reports['nonio']['passed'],
  'firmwareFunctionalAgreement':reports['firmware']['functionalAgreement'],
  'serialCycleAgreement':reports['firmware']['serialCycleAgreement'],
  'knownLedTransitionAgreement':reports['firmware']['realLedTransitionAgreement'],
  'writeWaitHalfEdgeAcceptance':False,'interruptedRepeatFlags':False,
  'rawPinAndStartupQualification':False,'crossCoreArbitration':False,
 },'boundary':'Reference Z80 digital candidate. Normal-completion I/O flags and read WAIT have independent oracles. Non-I/O checks compare each core before/after, not cross-core conformance. CHIPS has no BUSRQ/BUSACK interface. Interrupted repeats, write WAIT, raw pin/startup acceptance and production adoption remain open; no U880 specimen calibration is claimed.'}


def verify_capture(name,r,folder):
 for p,digest in r['sources'].items():
  if sha(ROOT/p)!=digest:raise ValueError('Producer changed: '+p)
 for p,digest in artifacts(name,r).items():
  if sha(folder/p)!=digest:raise ValueError('Capture changed: '+name+'/'+p)
 if name=='flags':
  assert not r['quick']
  assert [(x['opcode'],x['data'],x['b'],x['registerC'],x['l'],x['initialFlags']) for x in r['cases']]==list(vectors())
  disagreements=0
  for row in r['cases']:
   target=expected(row['opcode'],row['data'],row['b'],row['registerC'],row['l'],row['initialFlags'])
   c=parse(folder/str(row['id'])/'c.txt');h=parse(folder/str(row['id'])/'candidate.txt');old=parse(folder/str(row['id'])/'original.txt')
   assert target==row['expected']==row['candidate']==row['c']==c['FINAL'][-1][1]==h['AF'][-1][1]
   assert c['FINAL'][-1][-1]==1 and old['HALT']==h['HALT']==[[1]]
   assert old['RAM']==h['RAM'] and old['OUT']==h['OUT']
   assert old['AF'][-1][1]==row['original']
   disagreements+=row['original']!=target
  assert disagreements==r['originalDisagreements'] and disagreements>0 and r['cPass'] and r['candidatePass']
 elif name=='wait':
  negatives={'old-c':False,'old-hdl':False}
  for row in r['cases']:
   sample=3
   while row['start']<=sample<row['stop']:sample+=2
   assert row['expectedWidth']==sample+2
   for profile in ('old','candidate'):
    for lang in ('c','hdl'):
     p=folder/profile/(f"{row['instruction']}-{lang}-{row['start']}-{row['stop']}.txt")
     values={f[0]:int(f[1]) for line in p.read_text().splitlines() if (f:=line.split()) and f[0] in ('RELEASE','WIDTH','HALT','A')}
     actual={'width':values.get('RELEASE',values.get('WIDTH')),'halt':values['HALT'],'data':values['A']}
     assert actual==row[profile+'-'+lang] and actual['halt']==1
     if profile=='candidate':assert actual['width']==sample+2
     else:negatives[profile+'-'+lang]|=actual['width']!=sample+2
  assert negatives==r['negativeControls'] and all(negatives.values()) and r['passed']
 elif name=='nonio':
  for row in r['cases']:
   for lang in ('c','hdl'):
    if lang=='c' and row['mode']==4:continue
    logs=[]
    for profile in ('original','candidate'):
     path=folder/profile/(f"{lang}-im{row['im']}-mode{row['mode']}.txt")
     logs.append([l for l in path.read_text().splitlines() if l.startswith(('PIN ','RESULT '))])
    assert logs[0]==logs[1] and row[lang+'Unchanged']
    values=list(map(int,logs[1][-1].split()[1:]));assert values==row[lang+'Result']
    assert values[0]==0x5a and values[2]==(0x6d if row['mode'] in (1,2) else 0)
    assert row['mode']!=1 or values[3]>0
    assert row['mode']!=4 or values[4]>0
    assert row[lang+'Expected']
  assert r['passed']
 elif name=='instructions':
  for row in r['lateCases']:
   c,h=[parse(folder/row['id']/p) for p in ('half.txt','hdl.txt')]
   assert c['RAM']==h['RAM'] and [e[1:] for e in c['OUT']]==[e[1:] for e in h['OUT']]
   assert c['FINAL'][-1][:2]==h['AF'][-1] and row['agreement'] and row['flagsAgreement']
  assert r['allLateCasesAgree'] and r['functionalAgreement']
 elif name=='firmware':
  assert [r['scenario'] for r in r['cases']]==scenarios()+[{'id':'baseline-repeat-release-reset','cycles':4600000,'events':[]}]
  for row in r['cases']:
   spec=row['scenario']
   c,co=observation_window(firmware_parse(folder/spec['id']/'c.txt'),spec['cycles'])
   h,ho=observation_window(firmware_parse(folder/spec['id']/'hdl.txt'),spec['cycles'])
   assert int(c['LED'][-1][0])==int(h['LED'][-1][0])==(spec['cycles']//200000)*200000-1
   rebuilt=assess(spec,c,h)
   for key,value in rebuilt.items():
    assert row[key]==value,(spec['id'],key)
   assert row['outsideObservationInterval']=={'c':co,'hdl':ho}
   assert c['EDGE'][1:]==h['EDGE'][1:] and row['realLedTransitionsEquivalent']
   assert row['initialLedObservations']=={'c':c['EDGE'][:1],'hdl':h['EDGE'][:1]}
  assert all(r[k] for k in ('functionalAgreement','serialCycleAgreement','realLedTransitionAgreement'))


def main():
 ap=argparse.ArgumentParser();ap.add_argument('--retain',action='store_true');a=ap.parse_args()
 if a.retain:
  REPORTS.mkdir(parents=True,exist_ok=True)
  reports={name:json.loads((ROOT/'build'/path/'assessment.json').read_text()) for name,path in RUNS.items()}
  with tempfile.TemporaryDirectory() as temp:
   stage=Path(temp)
   for name,r in reports.items():
    run=ROOT/'build'/RUNS[name]
    verify_capture(name,r,run)
    (REPORTS/(name+'.json')).write_text(json.dumps(r,indent=2)+'\n')
    for p in artifacts(name,r):
     dest=stage/name/p;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(run/p,dest)
   with (REPORTS/'captures.tar.gz').open('wb') as f:
    with gzip.GzipFile(filename='',fileobj=f,mode='wb',mtime=0) as gz:
     with tarfile.open(fileobj=gz,mode='w') as tar:
      for p in sorted(stage.rglob('*')):
       if p.is_file():
        data=p.read_bytes();info=tarfile.TarInfo(str(p.relative_to(stage)));info.size=len(data);info.mode=0o644;tar.addfile(info,io.BytesIO(data))
  (REPORTS/'summary.json').write_text(json.dumps(verdict(reports),indent=2)+'\n')
  receipt={'verifierSha256':sha(Path(__file__)),'files':{p.name:sha(p) for p in sorted(REPORTS.iterdir()) if p.is_file() and p.name!='receipt.json'}}
  (REPORTS/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
 receipt=json.loads((REPORTS/'receipt.json').read_text());assert receipt['verifierSha256']==sha(Path(__file__))
 for p,d in receipt['files'].items():assert sha(REPORTS/p)==d,p
 reports={name:json.loads((REPORTS/(name+'.json')).read_text()) for name in RUNS}
 with tempfile.TemporaryDirectory() as temp:
  stage=Path(temp);extract(REPORTS/'captures.tar.gz',stage)
  for name,r in reports.items():verify_capture(name,r,stage/name)
 assert json.loads((REPORTS/'summary.json').read_text())==verdict(reports)
 print('I/O boundary captures reassessed; scoped gates pass, promotion remains open.')
if __name__=='__main__':main()
