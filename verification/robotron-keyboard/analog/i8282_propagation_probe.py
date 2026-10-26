#!/usr/bin/env python3
"""Constrain internal delay after accounting for loaded output-stage response."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from bus_switching_probe import duration,measurement,ALLOWANCE
from i8282_capacitance_probe import cases as cap_cases,deck as cap_deck,SOURCES as CAP_SOURCES
from ttl7406_probe import sha

HERE=Path(__file__).resolve().parent
SOURCES=('i8282_propagation_probe.py','i8282_delay_contract.json','i8282_timing.v',*CAP_SOURCES)


def cases():
    limits=json.loads((HERE/'bus_switching_limits.json').read_text())
    delay=json.loads((HERE/'i8282_delay_contract.json').read_text())
    low=json.loads((HERE/'bus_limits.json').read_text())['profiles']['I8282']['outputLow']
    rlow=low['maximumVolts']/low['sinkAmps']
    for c in cap_cases():
        load=dict(limits['switchingLoad']);load['capacitanceFarads']+=c['extraCapacitancePf']*1e-12
        old_drive=0 if c['kind']=='rise' else c['supplyVolts']
        old_r=rlow if c['kind']=='rise' else c['highOhms']
        initial=(old_drive/old_r+load['biasVolts']/load['resistanceOhms'])/(1/old_r+1/load['resistanceOhms'])
        seconds=duration(c['driveVolts'],c['resistanceOhms'],load,initial,delay['measurementVolts'])
        yield dict(c,initialVolts=initial,measurementVolts=delay['measurementVolts'],stageDelaySeconds=seconds,
                   maximumInternalDataDelaySeconds=delay['inputToOutputMaximumSeconds']-seconds,
                   maximumInternalStrobeDelaySeconds=delay['strobeToOutputMaximumSeconds']-seconds)


def deck(c):
    s=re.sub(r' IC=\S+',f' IC={c["initialVolts"]:.17g}',cap_deck(c))
    s=re.sub(r'^(Cdevice out 0 \S+)$',lambda m:m[1]+f' IC={c["initialVolts"]:.17g}',s,flags=re.M)
    direction='RISE' if c['kind']=='rise' else 'FALL'
    return re.sub(r'^meas tran edge_time .+$',f'meas tran edge_time WHEN v(out)={c["measurementVolts"]} {direction}=1',s,flags=re.M)


def verify(out):
    r=json.loads((out/'assessment.json').read_text())
    if r.get('completed') is not True or r.get('qualified') is not False or r.get('deviceAdmitted') is not False:raise ValueError('Invalid admission status')
    if r['sources']!={n:sha(HERE/n) for n in SOURCES}:raise ValueError('Stale sources')
    expected=list(cases())
    if len(r['cases'])!=len(expected):raise ValueError('Missing cases')
    for i,(c,a) in enumerate(zip(expected,r['cases'])):
        p=out/str(i)
        if a['case']!=c or (p/'probe.cir').read_text()!=deck(c):raise ValueError('Changed conditions')
        if a['files']!={n:sha(p/n) for n in ('probe.cir','ngspice.log')}:raise ValueError('Changed evidence')
        value=measurement((p/'ngspice.log').read_text())
        if a['measuredStageSeconds']!=value or abs(value-c['stageDelaySeconds'])>ALLOWANCE:raise ValueError('Invalid propagation measurement')
        if min(c['maximumInternalDataDelaySeconds'],c['maximumInternalStrobeDelaySeconds'])<=0:raise ValueError('No internal delay headroom')
    print('Loaded output-stage delay budgets verified; no internal delay or device model is admitted.')


def run(out,executable):
    out=out.resolve();out.mkdir(parents=True,exist_ok=False)
    engine=Path(shutil.which(executable) or executable).resolve();runtime={'path':str(engine),'sha256':sha(engine)}
    (out/'spinit').write_text('* Loaded output-stage propagation tests\n')
    r={'completed':False,'qualified':False,'deviceAdmitted':False,'runtime':runtime,
       'scope':'Step response from the opposite loaded steady state to the published 1.5-V pin threshold. Applies only to the explicit linear enabled-output hypotheses.',
       'interpretation':'Subtract measured/analytic output-stage response from the published loaded pin delay before assigning internal data or strobe delay. Using the full published maximum as internal delay and then adding this output stage exceeds the same pin limit.',
       'hdlBoundary':'i8282_timing.v is a digital guarantee/unknown envelope, not a calibrated internal-drive transition. This experiment does not change or invalidate that standalone envelope; it constrains any future electrical adapter.',
       'notEstablished':['Internal transistor timing','Enable and release timing','Temperature dependence','Nonlinear I/V','Device/specimen admission'],
       'sources':{n:sha(HERE/n) for n in SOURCES},'cases':[]}
    for i,c in enumerate(cases()):
        p=out/str(i);p.mkdir();(p/'probe.cir').write_text(deck(c))
        process=subprocess.run([str(engine),'-n','-b','probe.cir'],cwd=p,env=dict(os.environ,SPICE_SCRIPTS=str(out)),capture_output=True,text=True,timeout=30)
        log=process.stdout+process.stderr;(p/'ngspice.log').write_text(log);process.check_returncode()
        value=measurement(log)
        if abs(value-c['stageDelaySeconds'])>ALLOWANCE:raise ValueError('RC solution mismatch')
        r['cases'].append({'case':c,'measuredStageSeconds':value,'files':{n:sha(p/n) for n in ('probe.cir','ngspice.log')}})
    if sha(engine)!=runtime['sha256']:raise ValueError('Changed runtime')
    r['completed']=True;(out/'assessment.json').write_text(json.dumps(r,indent=2)+'\n');verify(out)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--ngspice',default='ngspice');p.add_argument('--verify',action='store_true');a=p.parse_args()
    if a.verify:verify(a.out)
    else:run(a.out,a.ngspice)
