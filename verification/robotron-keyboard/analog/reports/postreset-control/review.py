from pathlib import Path
import json,math,re,sys
HERE=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(HERE))
from compare_firmware_io import sha
from bus_observation import measure
from filter_truncation_log import diagnostic
from live_raw_review import signal_name
from raw_waveform import header,rows
from trace_io import open_binary,open_text
from serial_observation import validate_transport
root=Path(sys.argv[1]);r=json.loads((root/'run.json').read_text())
assert r['exitCode']==0 and not r['timedOut'] and not r['solverDiagnostic']
assert r['rawOutput'] and r['haltNs'] is None
assert sha(root/'capture-generator.py')==r['generatorSha256']
assert sha(root/'io.cir')==r['deckSha256']
for name,digest in r['inputs'].items():assert sha(root/name)==digest
storage=r['compressedOutput'];assert not storage['error']
assert sha(root/'waveform.raw')==storage['streams']['waveform.raw']['sha256']
with open_text(root/'ngspice.log') as stream:log=stream.read()
assert not diagnostic(log) and 'SORRY:' not in log
counts=re.findall(r'No\. of Data Rows\s*:\s*(\d+)',log);assert len(counts)==1
count=int(counts[0]);end=r['stopNs']*1e-9
with open_binary(root/'waveform.raw') as stream:
 names,declared=header(stream);assert declared in (0,count)
 assert set(map(signal_name,names))=={'time',*map(signal_name,r['observationSignals'])}
 for index,sample in enumerate(rows(stream,len(names),count)):
  if index==0:assert sample[0]==0
 assert abs(sample[0]-end)<=2*math.ulp(end)
rom=bytes(int(v,16) for v in (root/'s600.hex').read_text().split())
try:bus={'passed':True,'assessment':measure(log,root/'waveform.raw',r['stepNs'],rom,trace_extent=(0,end),raw_count=count)}
except ValueError as exc:bus={'passed':False,'error':str(exc),'details':getattr(exc,'details',None)}
try:serial={'passed':True,'assessment':validate_transport(log)}
except ValueError as exc:serial={'passed':False,'error':str(exc),'details':getattr(exc,'details',None)}
result={'completed':True,'qualified':False,'samples':count,'endSeconds':end,'bus':bus,'serial':serial,
        'reviewSourceSha256':sha(Path(__file__)),
        'artifacts':{name:sha(root/name) for name in ('run.json','io.cir','ngspice.log','waveform.raw')},
        'boundary':'Complete longer-window control only. No timestep-refinement, coupled rollback or full-repeat claim.'}
result['reviewDependencies']={n:sha(HERE/n) for n in ('compare_firmware_io.py','bus_observation.py','filter_truncation_log.py','live_raw_review.py','raw_waveform.py','trace_io.py','serial_observation.py')}
(root/'assessment.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
