from pathlib import Path
import sys,json,hashlib
sys.path.insert(0,str(Path('verification/robotron-keyboard/analog').resolve()))
from audit_log import records
root=Path('build/keyboard-controller-analog');out=root/'postreset-refinement-events';out.mkdir(exist_ok=False)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
summary={}
for step,name in ((25,'postreset-startup-combined'),(12.5,'postreset-combined-refinement-12.5'),(6.25,'postreset-combined-refinement-6.25')):
 folder=root/name;source=folder/'ngspice.log.xz';digest=sha(source);events=[]
 for line in records(folder/'ngspice.log',('TIME_AUDIT output ',)):
  fields=dict(x.split('=',1) for x in line.split()[2:]);fields.update({k:float(fields[k]) for k in ('actual','target','base')});events.append(fields)
 assert sha(source)==digest
 (out/f'{step}.json').write_text(json.dumps({'sourceCompressedSha256':digest,'events':events},indent=2)+'\n')
 summary[str(step)]={'events':len(events),'peakWindow':[e for e in events if .0011089<e['target']<.0011091]}
(out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2))
