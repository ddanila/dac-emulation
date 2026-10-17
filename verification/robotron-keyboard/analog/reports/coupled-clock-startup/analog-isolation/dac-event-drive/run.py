from pathlib import Path
import sys,subprocess,shutil,json,hashlib,re
root=Path('/Users/ddanila/fun/dac-emulation');h=root/'verification/robotron-keyboard/analog';sys.path.insert(0,str(h))
from ngspice_runtime import identify,verify
from failure_evidence import solver_diagnostic
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
src=root/'build/keyboard-controller-analog/analog-adc-observers'
p=root/'build/keyboard-controller-analog/dac-event-drive';p.mkdir(exist_ok=False)
original=(src/'probe.cir').read_text()
reference=root/'build/keyboard-controller-analog/powerup-drive/released/probe.cir'
bridges=[line for line in reference.read_text().splitlines() if line.startswith(('Adac ','Acolumns ','.model observation '))]
assert len(bridges)==3
outputs='dsink csink led1 led0 '+' '.join(f'dcol{i}' for i in range(12,-1,-1))
bridges += [f'Areplay [{outputs}] replay', '.model replay d_source(input_file="stimulus.txt")']
shutil.copy2(h/'reports/coupled-clock-startup/precise-replay/stimulus.txt',p/'stimulus.txt')
deck='\n'.join(line for line in original.splitlines() if not line.startswith('Vfixed_'))+'\n'
deck=deck.replace('.control','\n'.join(bridges)+'\n.control')
(p/'probe.cir').write_text(deck);shutil.copy2(src/'ls_nand_nominal.cir',p/'ls_nand_nominal.cir')
runtime,env=identify('/tmp/robotron-ngspice-switch/install/bin/ngspice-unpatched')
r={'completed':False,'qualified':False,'scope':'Startup isolation with ADC observers and original output DACs driven by captured digital events with unknown states mapped to zero volts; event times originate from the original midpoint-unknown profile; no CPU, firmware or full-board qualification','sourceDirectory':str(src.relative_to(root)),'sourceDeckSha256':sha(src/'probe.cir'),'sourceReportSha256':sha(src/'report.json'),'observerSourceDeckSha256':sha(reference),'ngspiceRuntime':runtime,'maximumStepNs':.0625,'durationUs':150,'retainedDirectory':str(p.relative_to(root))}
try:
 with (p/'ngspice.log').open('w') as log:proc=subprocess.run([runtime['executable']['path'],'-n','-b','probe.cir'],cwd=p,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=240)
 verify(runtime);r['exitCode']=proc.returncode;r['solverDiagnostic']=solver_diagnostic((p/'ngspice.log').read_text())
 if (p/'endpoint.txt').exists():r['endpointSeconds']=float((p/'endpoint.txt').read_text().split('=')[-1])
 r['completed']=proc.returncode==0 and not r['solverDiagnostic'] and abs(r.get('endpointSeconds',0)-150e-6)<1e-15
except Exception as e:r['error']=str(e)
r['artifacts']={f.name:{'sha256':sha(f),'bytes':f.stat().st_size} for f in p.iterdir() if f.is_file()}
(p/'report.json').write_text(json.dumps(r,indent=2)+'\n');print(r['completed'],r.get('endpointSeconds'),r.get('solverDiagnostic'),r.get('error'))
