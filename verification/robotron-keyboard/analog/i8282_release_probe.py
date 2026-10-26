#!/usr/bin/env python3
"""Measure passive release response and internal-disconnect timing headroom."""
import argparse
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
from bus_switching_probe import measurement,ALLOWANCE
from i8282_enabled_candidates import HIGH_OHMS
from i8282_capacitance_probe import EXTRA_PF,SOURCES as CAP_SOURCES
from ttl7406_probe import sha

HERE=Path(__file__).resolve().parent
SOURCES=('i8282_release_probe.py','i8282_release_contract.json',*CAP_SOURCES)


def cases():
    spec=json.loads((HERE/'i8282_release_contract.json').read_text())
    profile=json.loads((HERE/'bus_limits.json').read_text())['profiles']['I8282']
    supply=json.loads((HERE/'bus_device_contract.json').read_text())['devices']['I8282']['supplyRangeVolts']
    rlow=profile['outputLow']['maximumVolts']/profile['outputLow']['sinkAmps']
    leakage=profile['floatLeakage']['maximumMagnitudeAmps']
    for rhigh in HIGH_OHMS:
        for vcc in (supply[0],5.,supply[1]):
            for cap in EXTRA_PF:
                for high in (True,False):
                    rload=spec['highLoadOhms'] if high else spec['lowLoadOhms'];rdrive=rhigh if high else rlow
                    initial=((vcc if high else 0)/rdrive+spec['biasVolts']/rload)/(1/rdrive+1/rload)
                    target=initial+(-1 if high else 1)*spec['outputDepartureVolts']
                    capacitance=spec['externalCapacitanceFarads']+cap*1e-12
                    for current in (-leakage,0.,leakage):
                        final=spec['biasVolts']-current*rload
                        seconds=rload*capacitance*math.log((initial-final)/(target-final))
                        if not .45<=min(initial,target,final)<=max(initial,target,final)<=5.25:raise ValueError('Outside specified leakage domain')
                        yield {'highOhms':rhigh,'supplyVolts':vcc,'extraCapacitancePf':cap,'releasedFrom':'high' if high else 'low',
                               'loadOhms':rload,'biasVolts':spec['biasVolts'],'capacitanceFarads':capacitance,
                               'initialVolts':initial,'targetVolts':target,'leakageAmps':current,'finalVolts':final,
                               'stageSeconds':seconds,'maximumInternalDisconnectSeconds':spec['maximumDisableSeconds']-seconds}


def deck(c):
    edge='FALL' if c['releasedFrom']=='high' else 'RISE'
    return '\n'.join(['I8282 published disable-load response',f'Vbias bias 0 {c["biasVolts"]:.17g}',
        f'Rload bias out {c["loadOhms"]:.17g}',f'Cleffective out 0 {c["capacitanceFarads"]:.17g} IC={c["initialVolts"]:.17g}',
        f'Ileak out 0 {c["leakageAmps"]:.17g}', '.options reltol=1e-8 abstol=1e-12','.control',
        'tran 0.01n 100n 0 0.01n uic',f'meas tran edge_time WHEN v(out)={c["targetVolts"]:.17g} {edge}=1',
        'quit','.endc','.end',''])


def verify(out):
    r=json.loads((out/'assessment.json').read_text());expected=list(cases())
    if r.get('completed') is not True or r.get('qualified') is not False or r.get('deviceAdmitted') is not False:raise ValueError('Invalid admission status')
    if r['sources']!={n:sha(HERE/n) for n in SOURCES} or len(r['cases'])!=len(expected):raise ValueError('Changed sources or scope')
    for i,(c,a) in enumerate(zip(expected,r['cases'])):
        p=out/str(i)
        if a['case']!=c or (p/'probe.cir').read_text()!=deck(c):raise ValueError('Changed conditions')
        if a['files']!={n:sha(p/n) for n in ('probe.cir','ngspice.log')}:raise ValueError('Changed evidence')
        value=measurement((p/'ngspice.log').read_text())
        if a['measuredSeconds']!=value or abs(value-c['stageSeconds'])>ALLOWANCE:raise ValueError('Invalid release measurement')
        if not 0<c['maximumInternalDisconnectSeconds']<2.5e-8:raise ValueError('No internal delay headroom')
    print('I8282 disable-load budgets verified; enable and complete device admission remain open.')


def run(out,executable):
    out=out.resolve();out.mkdir(parents=True,exist_ok=False)
    engine=Path(shutil.which(executable) or executable).resolve();runtime={'path':str(engine),'sha256':sha(engine)}
    (out/'spinit').write_text('* Passive release plus bounded leakage hypotheses\n')
    r={'completed':False,'qualified':False,'deviceAdmitted':False,'runtime':runtime,
       'scope':'Published disable loads and 0.1-V output departure. Enabled initial state is the explicit resistor hypothesis; released output has constant leakage at zero and both published magnitude bounds. No internal disconnect delay is chosen.',
       'interpretation':'The published loaded disable maximum includes passive output response. Its remainder is the permissible internal-disconnect delay for each hypothesis, not a measured device delay. Cases do not admit combinations rejected by rise-time tests.',
       'notEstablished':['Enable thresholds and dynamics','Actual internal disconnect behavior','Voltage-dependent leakage','Nonlinear I/V and capacitance','Specimen applicability'],
       'sources':{n:sha(HERE/n) for n in SOURCES},'cases':[]}
    for i,c in enumerate(cases()):
        p=out/str(i);p.mkdir();(p/'probe.cir').write_text(deck(c))
        process=subprocess.run([str(engine),'-n','-b','probe.cir'],cwd=p,env=dict(os.environ,SPICE_SCRIPTS=str(out)),capture_output=True,text=True,timeout=30)
        log=process.stdout+process.stderr;(p/'ngspice.log').write_text(log);process.check_returncode();value=measurement(log)
        if abs(value-c['stageSeconds'])>ALLOWANCE:raise ValueError('RC solution mismatch')
        r['cases'].append({'case':c,'measuredSeconds':value,'files':{n:sha(p/n) for n in ('probe.cir','ngspice.log')}})
    if sha(engine)!=runtime['sha256']:raise ValueError('Changed runtime')
    r['completed']=True;(out/'assessment.json').write_text(json.dumps(r,indent=2)+'\n');verify(out)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--ngspice',default='ngspice');p.add_argument('--verify',action='store_true');a=p.parse_args()
    if a.verify:verify(a.out)
    else:run(a.out,a.ngspice)
