#!/usr/bin/env python3
"""Retain complete host waveforms and reassess the matched accumulation experiment."""
import argparse,hashlib,json,lzma,shutil,subprocess,sys
from pathlib import Path
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
p=argparse.ArgumentParser();p.add_argument('root',type=Path);a=p.parse_args();out=Path(__file__).resolve().parent
subprocess.run([sys.executable,str(out/'assess.py'),str(a.root),'--out',str(out/'assessment.json')],check=True)
retained={}
for mode in ('off','coarse','fine','quarter'):
 src=a.root/('host-device-'+mode);dest=out/mode;dest.mkdir(exist_ok=True)
 report=json.loads((src/'report.json').read_text());receipt=json.loads((src/'device-control.json').read_text())
 if receipt['reportSha256']!=sha(src/'report.json'):raise ValueError('Changed report')
 for name,digest in report['artifacts'].items():
  if sha(src/name)!=digest:raise ValueError('Changed artifact: '+name)
 for name in ('report.json','device-control.json','build-provenance.json','io.cir'):shutil.copyfile(src/name,dest/name)
 for name in ('ngspice.log','host-trace.txt'):
  with (src/name).open('rb') as source,lzma.open(dest/(name+'.xz'),'wb',preset=3) as target:shutil.copyfileobj(source,target)
 retained[mode]={'localRawDirectory':str(src),'compressed':{name:sha(src/name) for name in ('ngspice.log','host-trace.txt')},'localOnly':{name:report['artifacts'][name] for name in ('trace.txt','driver-trace.txt','boundary-trace.txt')}}
manifest={'scope':__doc__,'retained':retained,'files':{str(f.relative_to(out)):sha(f) for f in sorted(out.rglob('*')) if f.is_file() and f.name!='manifest.json'}}
(out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');print(out/'manifest.json')
