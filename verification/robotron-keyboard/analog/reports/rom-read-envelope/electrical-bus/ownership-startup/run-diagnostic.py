from pathlib import Path
import hashlib,json,os,subprocess,sys
root=Path(__file__).resolve().parent
sys.path.insert(0,str(Path('verification/robotron-keyboard/analog').resolve()))
from ngspice_runtime import verify
from failure_evidence import solver_diagnostic
from bus_observation import measure,BusMismatch
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
prepared=json.loads((root/'report.json').read_text())
deck=root/'io.cir';old=deck.read_text()
assert old.count('.tran 5.0n 30000000n')==1
(root/'prepared-io.cir').write_text(old)
deck.write_text(old.replace('.tran 5.0n 30000000n','.tran 5.0n 1600000n'))
report={'qualified':False,'completed':False,'preparedReportSha256':sha(root/'report.json'),
 'preparedDeckSha256':sha(root/'prepared-io.cir'),'diagnosticDeckSha256':sha(deck),
 'stopSeconds':.0016,'scriptSha256':sha(Path(__file__)),
 'boundary':'Short service-boundary diagnostic; only transient stop time differs from prepared single-press deck. Not the complete contact scenario or a qualification pass.'}
try:
 runtime=prepared['ngspiceRuntime'];verify(runtime)
 with (root/'ngspice.log').open('w') as log:
  result=subprocess.run([runtime['executable']['path'],'-n','-b','io.cir'],cwd=root,
   env=dict(os.environ,SPICE_SCRIPTS=str(Path(runtime['spinit']['path']).parent)),
   stdout=log,stderr=subprocess.STDOUT,timeout=300)
 report['exitCode']=result.returncode;result.check_returncode();verify(runtime)
 log=(root/'ngspice.log').read_text()
 if solver_diagnostic(log):raise ValueError('Solver diagnostics present')
 last=None;count=0
 with (root/'bus-trace.txt').open() as f:
  next(f)
  for line in f:last=float(line.split()[0]);count+=1
 if last is None or abs(last-report['stopSeconds'])>1e-12:raise ValueError('Incomplete trace')
 report['waveform']={'lastSeconds':last,'rows':count,'sha256':sha(root/'bus-trace.txt')}
 try:
  report['busObservation']=measure(log,root/'bus-trace.txt',5,Path('/Users/ddanila/fun/dac/public/media/robotron/s600.bin').read_bytes(),trace_extent=(0,.0016))
 except BusMismatch as error:
  report['busFailure']=error.details;report['busError']=str(error)
  drivers=error.details.get('drivers')
  report['allDriversReleasedAtFirstFailure']=bool(drivers) and all(set(bits)=={'0'} for d in drivers.values() for bits in d.values())
 report['completed']=True
except Exception as error:
 report['error']=str(error);raise
finally:
 if (root/'ngspice.log').exists():report['logSha256']=sha(root/'ngspice.log')
 (root/'ownership-assessment.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
