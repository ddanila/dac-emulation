#!/usr/bin/env python3
"""Reproduce ADC undefined-band/DAC threshold memory with the actual XSPICE models."""
import argparse,json,subprocess
from pathlib import Path
from ngspice_runtime import identify,verify
from analog_driver_replay import sha
from failure_evidence import solver_diagnostic

def deck(step):
 return f'''Undefined receiver boundary, not a physical 7406 model
Vcc supply 0 5
Vin source 0 PWL(0 0 10n 0 11n 1.4 30n 1.4 31n 5 50n 5 51n 1.4 70n 1.4 71n 0)
Ainput [source] [digital] receiver
.model receiver adc_bridge(in_low=.8 in_high=2)
Adac [digital] [intent] drive
.model drive dac_bridge(out_low=0 out_high=5 out_undef=2.5 t_rise=1n t_fall=1n)
Rpull supply output 1k
Sdriver output 0 intent 0 sink
.model sink SW(RON=20 ROFF=1t VT=2.5 VH=0)
.options reltol=1e-7 vntol=1e-9 abstol=1e-15
.control
set wr_singlescale
set wr_vecnames
set numdgt=17
tran {step}n 90n
wrdata trace.txt v(source) v(intent) v(output)
quit
.endc
.end
'''

def assess(rows):
 results=[]
 for lo,hi,on in ((15,25,False),(35,45,True),(55,65,True),(75,85,False)):
  selected=[r for r in rows if lo*1e-9<=r[0]<=hi*1e-9]
  if not selected:raise ValueError('Missing plateau')
  expected=5*20/1020 if on else 5e12/(1e12+1000)
  target=2.5 if lo in (15,55) else 5 if on else 0
  results.append({'windowNs':[lo,hi],'expectedOn':on,'maximumOutputErrorV':max(abs(r[3]-expected) for r in selected),'maximumIntentErrorV':max(abs(r[2]-target) for r in selected)})
 if any(r['maximumOutputErrorV']>1e-6 or r['maximumIntentErrorV']>1e-9 for r in results):raise ValueError('Unexpected plateau behavior')
 return results

def run(engine,spinit,out):
 runtime,env=identify(engine,spinit)
 for k in list(env):
  if k.startswith('ROBOTRON_'):env.pop(k)
 out.mkdir(parents=True,exist_ok=False);runs=[]
 for step in (.1,.05,.025):
  p=out/str(step);p.mkdir();(p/'probe.cir').write_text(deck(step))
  with (p/'ngspice.log').open('w') as log:
   result=subprocess.run([engine,'-n','-b','probe.cir'],cwd=p,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=30)
  if result.returncode or solver_diagnostic((p/'ngspice.log').read_text()):raise ValueError('Probe failed')
  rows=[list(map(float,l.split())) for l in (p/'trace.txt').read_text().splitlines()[1:]]
  if abs(rows[-1][0]-90e-9)>1e-18:raise ValueError('Incomplete probe')
  runs.append({'stepNs':step,'plateaus':assess(rows),'artifacts':{n:sha(p/n) for n in ('probe.cir','ngspice.log','trace.txt')}})
 verify(runtime)
 report={'passed':True,'qualified':False,'runtime':runtime,'runs':runs,'sourceSha256':sha(Path(__file__)),
 'finding':'The same 1.4 V undefined receiver input maps to 2.5 V DAC intent but retains opposite output switch states depending on prior logic. This is threshold memory, not a uniquely determined physical output.',
 'boundary':'No threshold, unknown value, load or switch parameter has been changed to choose a favorable result.'}
 (out/'assessment.json').write_text(json.dumps(report,indent=2)+'\n')
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--ngspice',required=True);p.add_argument('--spinit',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();run(a.ngspice,a.spinit,a.out.resolve())
