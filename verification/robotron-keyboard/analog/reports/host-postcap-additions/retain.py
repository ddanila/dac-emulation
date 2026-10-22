#!/usr/bin/env python3
"""Retain complete host waveforms and logs; other raw traces remain hash-bound locally."""
import argparse,hashlib,json,lzma,shutil,subprocess
from pathlib import Path
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
p=argparse.ArgumentParser();p.add_argument('root',type=Path);a=p.parse_args();out=Path(__file__).resolve().parent;retained={}
for mode in ('off','coarse','fine','quarter'):
 src=a.root/('host-postcap-'+mode);dest=out/mode;dest.mkdir(exist_ok=True)
 report=json.loads((src/'report.json').read_text());receipt=json.loads((src/'postcap-control.json').read_text())
 if receipt['reportSha256']!=sha(src/'report.json'):raise ValueError('Changed report')
 for name,digest in report['artifacts'].items():
  if sha(src/name)!=digest:raise ValueError('Changed artifact: '+name)
 for name in ['report.json','postcap-control.json','build-provenance.json','io.cir']:shutil.copyfile(src/name,dest/name)
 for name in ['ngspice.log','host-trace.txt']:
  with (src/name).open('rb') as source,lzma.open(dest/(name+'.xz'),'wb',preset=3) as target:shutil.copyfileobj(source,target)
 retained[mode]={'localRawDirectory':str(src),'compressed':{name:sha(src/name) for name in ['ngspice.log','host-trace.txt']},'localOnly':{name:report['artifacts'][name] for name in ['trace.txt','driver-trace.txt','boundary-trace.txt']}}
# Preserve the exact runner used before the fourth-step option was added.
root=out.parents[4]
old=subprocess.check_output(['git','show','b50e993:verification/robotron-keyboard/analog/reports/host-postcap-additions/run.py'],cwd=root)
(out/'captured-runner-v1.py').write_bytes(old)
summary=json.loads((out/'assessment.json').read_text())
manifest={'scope':__doc__,'retained':retained,'files':{str(f.relative_to(out)):sha(f) for f in sorted(out.rglob('*')) if f.is_file() and f.name!='manifest.json'}}
(out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(out/'manifest.json')
