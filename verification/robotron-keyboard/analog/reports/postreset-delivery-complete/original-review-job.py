from pathlib import Path
from types import SimpleNamespace
import json,os,subprocess,sys,time,traceback,shutil
base=Path('verification/robotron-keyboard/analog').resolve();sys.path.insert(0,str(base));local=Path('build/keyboard-controller-analog').resolve()
import postreset_delivery_capture as capture
from delivery_audit_review import scan
from raw_pair_review import compare_raw
from audit_log import equal
from postreset_startup_review import FIRMWARE
from compare_firmware_io import sha as logical_sha
from cached_net_board_review import sources
from reviewed_campaign_retention import files
from retained_evidence import check
from ttl7406_probe import sha
pid=12561;identity=subprocess.check_output(['ps','-p',str(pid),'-o','lstart=,command='],text=True).strip()
if 'delivery-audit-review-job.py' not in identity:raise ValueError('Wrong bounded reviewer')
pins=sources();status=local/'postreset-delivery-job.json';root=local/'postreset-delivery-on-25'
def save(state,**kw):status.write_text(json.dumps(dict(state=state,pid=os.getpid(),predecessorPid=pid,predecessorIdentity=identity,sources=pins,**kw),indent=2)+'\n')
def verify():
 if any(sha(base/n)!=h for n,h in pins.items()):raise ValueError('Changed diagnostic source')
try:
 save('waiting')
 while True:
  p=subprocess.run(['ps','-p',str(pid),'-o','lstart=,command='],text=True,capture_output=True)
  if p.returncode!=0:break
  if p.stdout.strip()!=identity:raise ValueError('Bounded reviewer PID reused')
  time.sleep(10)
 prior=json.loads((local/'delivery-audit-review-job.json').read_text())
 if prior['state']!='passed':raise ValueError('Bounded delivery audit did not pass')
 assessment=local/'delivery-audit-assessment.json'
 if sha(assessment)!=prior['assessmentSha256']:raise ValueError('Changed bounded assessment')
 verify()
 source=local/'delivery-audit-board';out=base/'reports/delivery-audit-board';before=files(source)
 shutil.copytree(source,out)
 if files(source)!=before or files(out)!=before:raise ValueError('Changed bounded retention')
 shutil.copy2(assessment,out/'assessment.json');shutil.copy2('/private/tmp/k7658-delivery-audit-vpi/vpi.c',out/'audit-vpi.c')
 (out/'manifest.json').write_text(json.dumps(dict(files=files(out),sources=pins),indent=2)+'\n');check(out)
 save('capturing',boundedRetained=str(out))
 capture.run(SimpleNamespace(source=base/'reports/postreset-adc/25',candidate=Path('/private/tmp/k7658-delivery-audit-vpi'),bounded_root=source,bounded_assessment=assessment,out=root,mode='on',step_ns=25,timeout=28800))
 verify();save('reviewing',boundedRetained=str(out))
 original=local/'postreset-drain-coarse';a=json.loads((original/'run.json').read_text());b=json.loads((root/'run.json').read_text())
 for folder,r in [(original,a),(root,b)]:
  if not r['completed'] or r.get('error'):raise ValueError('Incomplete full capture')
  if logical_sha(folder/'waveform.raw')!=r['storage']['waveform.raw']['sha256'] or logical_sha(folder/'ngspice.log')!=r['log']['sha256']:raise ValueError('Changed full capture')
 result=dict(qualified=False,comparison=compare_raw(original/'waveform.raw',root/'waveform.raw',[a['logSummary']['count'],b['logSummary']['count']],.00116,exact=True),audit=scan(root/'ngspice.log'),firmwareRecordsExactlyEqual=equal(original/'ngspice.log',root/'ngspice.log',FIRMWARE))
 if not result['firmwareRecordsExactlyEqual']:raise ValueError('Instrumentation changed full firmware')
 verify();(local/'postreset-delivery-assessment.json').write_text(json.dumps(result,indent=2)+'\n');save('passed',boundedRetained=str(out))
except Exception as exc:save('failed',error=str(exc),traceback=traceback.format_exc());raise
