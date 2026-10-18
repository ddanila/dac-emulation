import sys,json,hashlib,lzma
from pathlib import Path
root=Path.cwd();sys.path.insert(0,str(root/'verification/robotron-keyboard/analog'))
from serial_observation import validate_transport
from compare_firmware_io import compare
out=Path(__file__).resolve().parent
reports=[];transports=[];provenance={}
for kind in ('coarse','fine'):
 p=root/'build/keyboard-controller-analog'/('scenarios-repeat-'+kind)
 r=json.loads((p/'report.json').read_text()); log=(p/'ngspice.log').read_bytes();assert hashlib.sha256(log).hexdigest()==r['logSha256']
 t=validate_transport((p/'ngspice.log').read_text(),True);assert json.loads(json.dumps(t))==r['serialTransport']
 reports.append(r);transports.append(t)
 provenance[kind]={'reportSha256':hashlib.sha256((p/'report.json').read_bytes()).hexdigest(),'logSha256':r['logSha256'],'traceSha256':r['traceSha256']}
comparison=compare(*reports,*transports,15)
first=comparison['firstTimingDifference'];lo=min(first['coarseEventTimePs'],first['fineEventTimePs'])*1e-12-1e-6;hi=lo+2e-6
for kind in ('coarse','fine'):
 p=root/'build/keyboard-controller-analog'/('scenarios-repeat-'+kind)/'trace.txt.xz'
 digest=hashlib.sha256();rows=[]
 with lzma.open(p,'rb') as f:
  header=f.readline();digest.update(header)
  for line in f:
   digest.update(line);time=float(line.split()[0])
   if lo<=time<=hi:rows.append(line)
   if time>hi:break
  for chunk in iter(lambda:f.read(1024*1024),b''):digest.update(chunk)
 assert digest.hexdigest()==provenance[kind]['traceSha256']
 (out/(kind+'-window.txt')).write_bytes(header+b''.join(rows))
 print(kind,len(rows),'rows; raw waveform hash verified',flush=True)
result={'qualified':False,'scope':'Diagnostic review of archived repeat runs; original solver diagnostics remain unresolved. No simulations rerun or acceptance gates waived.','comparison':comparison,'inputs':provenance,'windowSeconds':[lo,hi]}
(out/'assessment.json').write_text(json.dumps(result,indent=2)+'\n')
