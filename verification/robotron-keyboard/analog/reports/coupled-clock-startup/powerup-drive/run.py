from pathlib import Path
import sys,subprocess,shutil,json,hashlib,re
root=Path('/Users/ddanila/fun/dac-emulation');h=root/'verification/robotron-keyboard/analog';sys.path.insert(0,str(h))
from ngspice_runtime import identify,verify
from failure_evidence import solver_diagnostic
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
src=root/'build/keyboard-controller-analog/coupled-clock-sixteenth-ns/fine'
original=(src/'clock-probe.cir').read_text()
assert original.count('tran 0.0625n 1000u')==1
runtime,env=identify('/tmp/robotron-ngspice-switch/install/bin/ngspice-unpatched')
for method, undefined_volts in (('released', 0), ('asserted', 5)):
 p=root/'build/keyboard-controller-analog/powerup-drive'/method;p.mkdir(parents=True,exist_ok=False)
 deck=original.replace('tran 0.0625n 1000u','tran 0.0625n 150u')
 assert deck.count('out_undef=2.5') == 1
 deck=deck.replace('out_undef=2.5',f'out_undef={undefined_volts}')
 deck=re.sub(r'^wrdata .*$', '',deck,flags=re.M)
 deck=deck.replace('\nquit\n','\nset numdgt=17\nwrdata trace.txt v(n_CLK)\nprint time[length(time)-1] > endpoint.txt\nquit\n')
 (p/'probe.cir').write_text(deck)
 for name in ('boot.vvp','s600.hex','ls_nand_nominal.cir'):shutil.copy2(src/name,p/name)
 r={'completed':False,'qualified':False,'scope':'150 us live TV80/S600 startup with explicit unknown-output analog projection; sensitivity fixture, not historical power-up state or full-board qualification','unknownOutputVolts':undefined_volts,'maximumStepNs':.0625,'durationUs':150,'sourceDirectory':str(src.relative_to(root)),'sourceDeckSha256':sha(src/'clock-probe.cir'),'sourceReportSha256':sha(src/'clock-probe.json'),'ngspiceRuntime':runtime,'sources':{n:sha(h/n) for n in ('ngspice_runtime.py','failure_evidence.py')},'retainedDirectory':str(p.relative_to(root))}
 try:
  verify(runtime)
  with (p/'ngspice.log').open('w') as log:proc=subprocess.run([runtime['executable']['path'],'-n','-b','probe.cir'],cwd=p,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=240)
  verify(runtime);r['exitCode']=proc.returncode;r['solverDiagnostic']=solver_diagnostic((p/'ngspice.log').read_text())
  if (p/'endpoint.txt').exists():r['endpointSeconds']=float((p/'endpoint.txt').read_text().split('=')[-1])
  r['completed']=proc.returncode==0 and not r['solverDiagnostic'] and abs(r.get('endpointSeconds',0)-150e-6)<1e-15
 except Exception as e:r['error']=str(e)
 r['artifacts']={f.name:{'sha256':sha(f),'bytes':f.stat().st_size} for f in p.iterdir() if f.is_file()}
 (p/'report.json').write_text(json.dumps(r,indent=2)+'\n');print(method,r['completed'],r.get('endpointSeconds'),r.get('solverDiagnostic'),flush=True)
