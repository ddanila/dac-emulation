#!/usr/bin/env python3
"""Isolate a captured bus read without changing its drivers, loads or supply history."""
import argparse,csv,json,math,re,shutil,subprocess,time
from pathlib import Path
from ttl7406_probe import sha
from failure_evidence import solver_diagnostic
HERE=Path(__file__).resolve().parent
TARGET=.00115850065

def validate(data,width=None):
 if len(data)<2 or any(len(r)!=(width or len(data[0])) or not all(math.isfinite(v) for v in r) for r in data):raise ValueError('Invalid waveform values or columns')
 if any(b[0]<=a[0] for a,b in zip(data,data[1:])):raise ValueError('Waveform time must increase strictly')
 return data

def rows(path,csv_format=False):
 if csv_format:
  with path.open() as stream:data=[list(map(float,r)) for r in list(csv.reader(stream))[1:]]
 else:data=[list(map(float,l.split())) for l in path.read_text().splitlines()[1:]]
 return validate(data)

def at(data,t):
 for a,b in zip(data,data[1:]):
  if a[0]<=t<=b[0]:
   f=(t-a[0])/(b[0]-a[0]);return [a[i]+f*(b[i]-a[i]) for i in range(1,len(a))]
 raise ValueError('Waveform does not bracket target')

def derive(deck):
 components=[l for l in deck.splitlines() if re.match(r'^(Cbus_\S+ n_D1 |Rbus_numerical1 |Bbus_(low|high)_(1|9|17) )',l)]
 if len(components)!=10:raise ValueError('Expected three capacitors, six drivers and numerical resistor')
 if next(l for l in components if l.startswith('Rbus')).split()[1:]!=['n_D1','0','1e12']:raise ValueError('Unexpected numerical shunt')
 capacitance=sum(float(l.split()[-1]) for l in components if l.startswith('Cbus'))
 drivers=[]
 for i in (1,9,17):
  values=[]
  for side in ('low','high'):
   line=next(l for l in components if l.startswith(f'Bbus_{side}_{i} '))
   values.append(float(re.search(r'\(5\*([\d.eE+-]+)\)',line)[1]))
  drivers.append(values)
 return components,capacitance,drivers

def rk4(data,capacitance,drivers,target,max_step):
 """Independent scalar KCL integration of the same piecewise-linear boundary."""
 voltage=data[0][1]
 for a,b in zip(data,data[1:]):
  if a[0]>=target:break
  end=min(b[0],target);n=max(1,math.ceil((end-a[0])/max_step));h=(end-a[0])/n
  def slope(t,v):
   f=(t-a[0])/(b[0]-a[0]);supply=a[2]+f*(b[2]-a[2]);current=-v/1e12
   for j,(low,high) in enumerate(drivers):
    lo=a[3+2*j]+f*(b[3+2*j]-a[3+2*j]);hi=a[4+2*j]+f*(b[4+2*j]-a[4+2*j])
    current+=(supply-v)*hi/(5*high)-v*lo/(5*low)
   return current/capacitance
  for k in range(n):
   t=a[0]+k*h;k1=slope(t,voltage);k2=slope(t+h/2,voltage+h*k1/2);k3=slope(t+h/2,voltage+h*k2/2);k4=slope(t+h,voltage+h*k3)
   voltage+=h*(k1+2*k2+2*k3+k4)/6
 return voltage

def assess(root):
 stimulus=json.loads((root/'stimulus.json').read_text());data=validate(stimulus['rows'],9);target=TARGET-data[0][0]
 _,capacitance,drivers=derive('\n'.join(stimulus['components']))
 if capacitance!=stimulus['capacitanceFarads'] or drivers!=stimulus['driverOhms']:raise ValueError('Changed circuit parameters')
 result={'completed':True,'qualified':False,'boundary':'Conditional replay of sampled supply/enables and captured initial capacitor voltage. It isolates this read; it does not qualify full-board solver convergence, semiconductor I/V or transient input applicability.','runs':{}}
 for name in ('default','tight','tighter','xyce'):
  folder=root/name;xyce=name=='xyce';log=(folder/('xyce.log' if xyce else 'ngspice.log')).read_text()
  receipt=json.loads((folder/'run.json').read_text())
  if xyce:
   # These nodes are grounded ideal boundary sources. Xyce counts only the
   # source terminal, not B-source voltage references; no node is floating.
   screened=re.sub(r'Netlist warning: Voltage Node \(BUS_(?:LOW|HIGH)_(?:1|9|17)\) connected to only 1 device\s+Terminal','',log)
   diagnostic=re.search(r'\b(?:warning|error|fatal|aborted)\b',screened,re.I)
   if 'End of Xyce(TM) Simulation' not in log:raise ValueError('Missing Xyce completion')
  else:diagnostic=solver_diagnostic(log)
  if receipt['exitCode'] or diagnostic:raise ValueError('Replay failed: '+name)
  samples=rows(folder/('probe.cir.csv' if xyce else 'trace.txt'),xyce)
  if samples[0][0]>2e-12 or abs(samples[-1][0]-(data[-1][0]-data[0][0]))>1e-12:raise ValueError('Incomplete replay')
  v,supply=at(samples,target);result['runs'][name]={'volts':v,'supplyVolts':supply,'excessVolts':v-supply,'firstSampleSeconds':samples[0][0]}
 result['independentKclVolts']=[rk4(data,stimulus['capacitanceFarads'],stimulus['driverOhms'],TARGET,h) for h in (1e-9,.25e-9)]
 estimates=[r['volts'] for r in result['runs'].values()]+result['independentKclVolts']
 result['observedSolverSpreadVolts']=max(estimates)-min(estimates)
 result['originalExcessVolts']=stimulus['originalVolts']-stimulus['originalSupplyVolts']
 result['replayExcessPersists']=min(r['excessVolts'] for r in result['runs'].values())>1e-6 and result['observedSolverSpreadVolts']<1e-9
 result['interpretation']='The isolated linear stress fixture retains charge above its falling supply. Agreement conditional on this recorded boundary does not resolve the coupled capture uncertainty or establish a specimen fault. Keep the published limit unchanged.'
 result['sourceSha256']=sha(Path(__file__));return result

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--verify',action='store_true');p.add_argument('--out',type=Path,required=True)
 p.add_argument('--capture',type=Path);p.add_argument('--source-deck',type=Path);p.add_argument('--ngspice');p.add_argument('--xyce');a=p.parse_args()
 if a.verify:
  for n,d in json.loads((a.out/'manifest.json').read_text()).items():
   if sha(a.out/n)!=d:raise ValueError('Changed evidence: '+n)
  if assess(a.out)!=json.loads((a.out/'assessment.json').read_text()):raise ValueError('Stale replay assessment')
  print('Recorded-boundary bus replay verified; full electrical acceptance remains open.');return
 if any(x is None for x in (a.capture,a.source_deck,a.ngspice,a.xyce)):p.error('Capture, source deck and both engines are required')
 a.out.mkdir(parents=True,exist_ok=False);deck=a.source_deck.read_text();components,capacitance,drivers=derive(deck)
 allrows=rows(a.capture);data=[r for r in allrows if .001154<=r[0]<=.0011586]
 if not data or len(data[0])!=9:raise ValueError('Expected supply and all six driver enables')
 original=next(r for r in data if r[0]==TARGET)
 stimulus={'captureSha256':sha(a.capture),'sourceDeckSha256':sha(a.source_deck),'components':components,'capacitanceFarads':capacitance,'driverOhms':drivers,'rows':data,'originalVolts':original[1],'originalSupplyVolts':original[2]}
 (a.out/'stimulus.json').write_text(json.dumps(stimulus,indent=2)+'\n')
 origin=data[0][0];stop=data[-1][0]-origin;lines=['Recorded D1 boundary: original driver and load equations']
 for line in components:
  if line.startswith('Cbus'):line+=f' IC={data[0][1]:.17g}'
  lines.append(line)
 signals=[('n_p5V',2)]+[(f'bus_{side}_{i}',3+2*j+k) for j,i in enumerate((1,9,17)) for k,side in enumerate(('low','high'))]
 for name,col in signals:lines.append(f'V_{name} {name} 0 PWL('+' '.join(f'{r[0]-origin:.17g} {r[col]:.17g}' for r in data)+')')
 for name,step,rel,vntol,abstol in [('default',5e-9,1e-3,1e-6,1e-12),('tight',1e-9,1e-6,1e-10,1e-16),('tighter',.25e-9,1e-9,1e-13,1e-19),('xyce',.25e-9,1e-9,1e-13,1e-19)]:
  folder=a.out/name;folder.mkdir();xyce=name=='xyce';engine=a.xyce if xyce else a.ngspice
  tail=([f'.OPTIONS TIMEINT RELTOL={rel} ABSTOL={vntol}',f'.TRAN {step:.17g} {stop:.17g} 0 {step:.17g} UIC','.PRINT TRAN FORMAT=CSV PRECISION=17 V(n_D1) V(n_p5V)','.END'] if xyce else [f'.options reltol={rel} vntol={vntol} abstol={abstol}','.control','set numdgt=17','set wr_singlescale','set wr_vecnames',f'tran {step:.17g} {stop:.17g} uic','wrdata trace.txt v(n_D1) v(n_p5V)','quit','.endc','.end'])
  (folder/'probe.cir').write_text('\n'.join(lines+tail)+'\n');command=[engine,*([] if xyce else ['-n','-b']),'probe.cir'];start=time.monotonic()
  run=subprocess.run(command,cwd=folder,capture_output=True,text=True,timeout=90);(folder/('xyce.log' if xyce else 'ngspice.log')).write_text(run.stdout+run.stderr)
  (folder/'run.json').write_text(json.dumps({'command':command,'executableSha256':sha(Path(engine)),'exitCode':run.returncode,'elapsedSeconds':time.monotonic()-start},indent=2)+'\n')
 (a.out/'assessment.json').write_text(json.dumps(assess(a.out),indent=2)+'\n')
 (a.out/'manifest.json').write_text(json.dumps({str(f.relative_to(a.out)):sha(f) for f in sorted(a.out.rglob('*')) if f.is_file()},indent=2)+'\n');print(a.out/'assessment.json')
if __name__=='__main__':main()
