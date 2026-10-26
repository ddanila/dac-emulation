#!/usr/bin/env python3
"""Constrained enabled-output alternatives, not complete I8282 device models."""
import argparse
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
from bus_switching_probe import duration, measurement, ALLOWANCE
from failure_evidence import solver_diagnostic
from ttl7406_probe import sha

HERE=Path(__file__).resolve().parent
# Two explicitly assumed interior points of the published-load feasible region.
# Neither value is extracted from a typical curve or chosen to fit board traffic.
HIGH_OHMS=(125.,250.)
SOURCES=('i8282_enabled_candidates.py','bus_switching_probe.py','bus_switching_limits.json',
         'bus_limits.json','bus_device_contract.json','bus_endpoint_candidates.py',
         'failure_evidence.py','ttl7406_probe.py')


def cases():
    limits=json.loads((HERE/'bus_switching_limits.json').read_text())
    dc=json.loads((HERE/'bus_limits.json').read_text())['profiles']['I8282']
    low=dc['outputLow']; high=dc['outputHigh']; rlow=low['maximumVolts']/low['sinkAmps']
    for rhigh in HIGH_OHMS:
        for supply in (limits['supplyRangeVolts'][0],5.,limits['supplyRangeVolts'][1]):
            for kind in ('dc-high','dc-low','rise','fall'):
                positive=kind in ('dc-high','rise'); drive=supply if positive else 0.
                resistance=rhigh if positive else rlow
                case={'highOhms':rhigh,'supplyVolts':supply,'kind':kind,'driveVolts':drive,'resistanceOhms':resistance}
                if kind.startswith('dc'):
                    current=high['sourceMagnitudeAmps'] if positive else -low['sinkAmps']
                    value=drive-current*resistance
                    case.update(loadAmps=current,expectedVolts=value,
                                limitVolts=high['minimumVolts'] if positive else low['maximumVolts'])
                else:
                    spec=limits[kind]
                    case.update(expectedSeconds=duration(drive,resistance,limits['switchingLoad'],spec['fromVolts'],spec['toVolts']),maximumSeconds=spec['maximumSeconds'])
                yield case


def deck(case):
    c=case; lines=['I8282 enabled-output candidate under published load',
        f'Vdrive drive 0 {c["driveVolts"]:.17g}',f'Rdriver drive out {c["resistanceOhms"]:.17g}']
    if c['kind'].startswith('dc'):
        lines += [f'Iload out 0 {c["loadAmps"]:.17g}', '.control','op','print v(out)']
    else:
        spec=json.loads((HERE/'bus_switching_limits.json').read_text());load=spec['switchingLoad'];edge=spec[c['kind']]
        direction='RISE' if c['kind']=='rise' else 'FALL'
        initial=0 if direction=='RISE' else c['supplyVolts']
        lines += [f'Vbias bias 0 {load["biasVolts"]:.17g}',f'Rload bias out {load["resistanceOhms"]:.17g}',
            f'Cload out 0 {load["capacitanceFarads"]:.17g} IC={initial:.17g}',
            '.options reltol=1e-8 abstol=1e-12','.control','tran 0.05n 200n 0 0.05n uic',
            f'meas tran edge_time TRIG v(out) VAL={edge["fromVolts"]} {direction}=1 TARG v(out) VAL={edge["toVolts"]} {direction}=1']
    return '\n'.join(lines+['quit','.endc','.end',''])


def evaluate(case,log):
    if solver_diagnostic(log): raise ValueError('Solver diagnostic')
    if case['kind'].startswith('dc'):
        values=re.findall(r'^v\(out\)\s*=\s*(\S+)',log,re.M)
        if len(values)!=1: raise ValueError('Missing/ambiguous DC result')
        value=float(values[0]);expected=case['expectedVolts']
        if not math.isfinite(value) or abs(value-expected)>1e-7: raise ValueError('DC solution mismatch')
        passed=value>=case['limitVolts'] if case['kind']=='dc-high' else value<=case['limitVolts']
        return {'measuredVolts':value,'withinPublishedLimit':passed}
    value=measurement(log)
    if abs(value-case['expectedSeconds'])>ALLOWANCE: raise ValueError('RC solution mismatch')
    return {'measuredSeconds':value,'withinPublishedLimit':value<=case['maximumSeconds']}


def verify(out):
    report=json.loads((out/'assessment.json').read_text())
    if report.get('completed') is not True or report.get('qualified') is not False or report.get('deviceAdmitted') is not False:
        raise ValueError('Invalid admission status')
    if report['sources']!={n:sha(HERE/n) for n in SOURCES}: raise ValueError('Stale sources')
    expected=list(cases())
    if len(expected)!=len(report['cases']): raise ValueError('Missing cases')
    for i,(case,actual) in enumerate(zip(expected,report['cases'])):
        folder=out/str(i)
        if actual['case']!=case or (folder/'probe.cir').read_text()!=deck(case): raise ValueError('Changed test conditions')
        if actual['files']!={n:sha(folder/n) for n in ('probe.cir','ngspice.log')}: raise ValueError('Changed evidence')
        result=evaluate(case,(folder/'ngspice.log').read_text())
        if actual['result']!=result or not result['withinPublishedLimit']: raise ValueError('Candidate fails published constraint')
    print('Enabled-output constraints pass; complete I8282 admission remains open.')


def run(out,executable):
    out=out.resolve();out.mkdir(parents=True,exist_ok=False)
    engine=Path(shutil.which(executable) or executable).resolve();runtime={'path':str(engine),'sha256':sha(engine)}
    (out/'spinit').write_text('* Isolated enabled-output tests\n')
    report={'completed':False,'qualified':False,'deviceAdmitted':False,'runtime':runtime,
        'scope':'Linear enabled-output hypotheses at rated supply endpoints and nominal supply. DC output tests and published loaded rise/fall tests only. No extra output capacitance or internal switching delay.',
        'interpretation':'Both choices replace the rejected DC-only high-side values for enabled-output studies. They are distinct feasible examples, not measured parameters or bounds on all possible I/V curves. Within this constant-resistance family, minimum supply is worst for loaded high voltage and rise time; low voltage and fall time are supply-independent.',
        'notEstablished':['Enable/disable and propagation timing','Output capacitance and nonlinear I/V','Temperature dependence','Reverse operation','Startup or brownout','Specimen applicability'],
        'sources':{n:sha(HERE/n) for n in SOURCES},'cases':[]}
    for i,case in enumerate(cases()):
        folder=out/str(i);folder.mkdir();(folder/'probe.cir').write_text(deck(case))
        p=subprocess.run([str(engine),'-n','-b','probe.cir'],cwd=folder,env=dict(os.environ,SPICE_SCRIPTS=str(out)),capture_output=True,text=True,timeout=30)
        log=p.stdout+p.stderr;(folder/'ngspice.log').write_text(log);p.check_returncode()
        result=evaluate(case,log)
        if not result['withinPublishedLimit']: raise ValueError('Rejected candidate')
        report['cases'].append({'case':case,'result':result,'files':{n:sha(folder/n) for n in ('probe.cir','ngspice.log')}})
    if sha(engine)!=runtime['sha256']:raise ValueError('Changed runtime')
    report['completed']=True;(out/'assessment.json').write_text(json.dumps(report,indent=2)+'\n');verify(out)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--ngspice',default='ngspice');p.add_argument('--verify',action='store_true');a=p.parse_args()
    if a.verify:verify(a.out)
    else:run(a.out,a.ngspice)
