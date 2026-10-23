#!/usr/bin/env python3
"""Exercise ADC crossing localization on a linear ramp with known threshold times."""
import argparse,json,subprocess,re,math
from pathlib import Path
from ngspice_runtime import identify,verify
from analog_driver_replay import sha
from failure_evidence import solver_diagnostic

def run(engine,spinit,out,rc=False):
 runtime,env=identify(engine,spinit);out.mkdir(parents=True,exist_ok=False);runs=[]
 for key in list(env):
  if key.startswith('ROBOTRON_'):env.pop(key)
 for enabled in (False,True):
  for step in (5,2.5,1.25):
   p=out/f'{"on" if enabled else "off"}-{step}';p.mkdir()
   deck=f'''Linear receiver threshold timing diagnostic
Vin source 0 PWL(0 0 10n 0 20n 5 30n 5 40n 0)
Ainput [source] [digital] receiver
.model receiver adc_bridge(in_low=.8 in_high=2)
Adac [digital] [intent] drive
.model drive dac_bridge(out_low=0 out_high=5 out_undef=2.5 t_rise=1p t_fall=1p)
Rload intent 0 1g
.options reltol=1e-7 vntol=1e-9 abstol=1e-15
.control
set wr_singlescale
set wr_vecnames
set numdgt=17
tran {step}n 50n 0 {step}n
wrdata trace.txt v(source) v(intent)
quit
.endc
.end
'''
   if rc:
    deck=deck.replace('Vin source 0 PWL(0 0 10n 0 20n 5 30n 5 40n 0)', 'Vin drive 0 PWL(0 0 10n 0 10.001n 5)\nRinput drive source 1k\nCinput source 0 10p')
   (p/'probe.cir').write_text(deck)
   run_env=dict(env,ROBOTRON_ADC_TRACE="1")
   if enabled:run_env['ROBOTRON_ADC_CROSSINGS']='1'
   with (p/'ngspice.log').open('w') as log:
    result=subprocess.run([engine,'-n','-b','probe.cir'],cwd=p,env=run_env,stdout=log,stderr=subprocess.STDOUT,timeout=30)
   diagnostic=solver_diagnostic((p/'ngspice.log').read_text())
   if result.returncode or diagnostic:raise ValueError(str(diagnostic))
   rows=[list(map(float,l.split())) for l in (p/'trace.txt').read_text().splitlines()[1:]]
   if abs(rows[-1][0]-50e-9)>1e-18:raise ValueError('Incomplete ramp probe')
   crossings=[]
   # Read the DAC target plateaus; its 1ps transition is included, never subtracted.
   for start,end,target in ((11.6,14,2.5),(14,30,5),(36,38.4,2.5),(38.4,50,0)):
    found=next((r[0] for r in rows if start*1e-9<=r[0]<end*1e-9 and abs(r[2]-target)<1e-9),None)
    crossings.append({'expectedThresholdSeconds':start*1e-9,'target':target,'firstTargetSampleSeconds':found,'delaySeconds':found-start*1e-9 if found is not None else None})
   event_records=[{'timeSeconds':float.fromhex(t),'value':float.fromhex(v),'old':int(old),'new':int(new)} for t,v,old,new in re.findall(r'ADC_CROSS time=(\S+) node=source value=(\S+) old=(\d+) new=(\d+)',(p/'ngspice.log').read_text())]
   if rc:crossings=[]
   expected_times=[0,11.6,14,36,38.4]
   expected_states=[0,2,1,2,0]
   if rc:
    # Exact RC response after a finite linear source ramp.
    amplitude=-math.expm1(-.001/10)*10/.001
    expected_times=[0,*[10.001-10*math.log((1-v/5)/amplitude) for v in (.8,2)]]
    expected_states=[0,2,1]
   if enabled:
    if [e['new'] for e in event_records]!=expected_states:raise ValueError('Unexpected ADC state sequence')
    if max(abs(e['timeSeconds']-t*1e-9) for e,t in zip(event_records,expected_times))>(1e-12 if rc else 1e-15):raise ValueError('Linear crossing timing failed')
   runs.append({'expectedTimesNs':expected_times,'events':event_records,'enabled':enabled,'stepNs':step,'crossings':crossings,'artifacts':{n:sha(p/n) for n in ('probe.cir','ngspice.log','trace.txt')}})
 verify(runtime);report={'crossingRegressionPassed':True,'curve':'RC' if rc else 'linear','qualified':False,'runtime':runtime,'runs':runs,'sourceSha256':sha(Path(__file__)),
 'boundary':'Analytic linear-ramp or RC crossings only. First DAC target sample includes DAC slew and sample spacing. Full nonlinear board and event rollback need separate controls.'}
 (out/'assessment.json').write_text(json.dumps(report,indent=2)+'\n')
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--rc',action='store_true');p.add_argument('--ngspice',required=True);p.add_argument('--spinit',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();run(a.ngspice,a.spinit,a.out.resolve(),a.rc)
