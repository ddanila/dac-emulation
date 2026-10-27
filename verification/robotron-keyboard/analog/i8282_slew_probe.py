#!/usr/bin/env python3
"""Screen finite I8282 drive ramps against loaded edge and propagation limits."""
import argparse
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
from i8282_propagation_probe import cases as baseline_cases, SOURCES as BASE_SOURCES
from u880_slew_probe import fraction
from bus_switching_probe import ALLOWANCE
from failure_evidence import solver_diagnostic
from ttl7406_probe import sha

HERE=Path(__file__).resolve().parent
SOURCES=tuple(sorted(set(('i8282_slew_probe.py','u880_slew_probe.py',*BASE_SOURCES))))


def voltage(c,t):
    decay=math.exp(-t/c['tauSeconds'])
    return c['startEquilibriumVolts']+(c['initialVolts']-c['startEquilibriumVolts'])*decay+(c['finalEquilibriumVolts']-c['startEquilibriumVolts'])*fraction(t,c['tauSeconds'],c['rampSeconds'])


def crossing(c,target):
    rising=c['kind']=='rise'
    if not min(c['initialVolts'],c['finalEquilibriumVolts'])<target<max(c['initialVolts'],c['finalEquilibriumVolts']):
        raise ValueError('Threshold outside complete excursion')
    lo,hi=0.,c['rampSeconds']+100*c['tauSeconds']
    for _ in range(100):
        mid=(lo+hi)/2
        if (voltage(c,mid)<target)==rising:lo=mid
        else:hi=mid
    return (lo+hi)/2


def cases():
    limits=json.loads((HERE/'bus_switching_limits.json').read_text())
    delays=json.loads((HERE/'i8282_delay_contract.json').read_text())
    load=limits['switchingLoad']
    for base in baseline_cases():
        base={k:v for k,v in base.items() if k not in ('expectedSeconds','withinPublishedLimit',
            'stageDelaySeconds','maximumInternalDataDelaySeconds','maximumInternalStrobeDelaySeconds')}
        for ramp in (0.,10e-9,30e-9,60e-9):
            r=base['resistanceOhms'];rl=load['resistanceOhms']
            start=0. if base['kind']=='rise' else base['supplyVolts']
            c=dict(base,rampSeconds=ramp,startDriveVolts=start,
                tauSeconds=(load['capacitanceFarads']+base['extraCapacitancePf']*1e-12)/(1/r+1/rl),
                startEquilibriumVolts=(start/r+load['biasVolts']/rl)/(1/r+1/rl),
                finalEquilibriumVolts=(base['driveVolts']/r+load['biasVolts']/rl)/(1/r+1/rl))
            edge=limits[c['kind']]
            c['crossings']={key:crossing(c,target) for key,target in (('from',edge['fromVolts']),('to',edge['toVolts']),('propagation',delays['measurementVolts']))}
            c['edgeSeconds']=c['crossings']['to']-c['crossings']['from']
            c['edgePassed']=c['edgeSeconds']<=edge['maximumSeconds']
            c['dataHeadroomSeconds']=delays['inputToOutputMaximumSeconds']-c['crossings']['propagation']
            c['strobeHeadroomSeconds']=delays['strobeToOutputMaximumSeconds']-c['crossings']['propagation']
            yield c


def budgets(rows):
    groups={}
    for i,c in enumerate(rows):
        key=(c['highOhms'],c['extraCapacitancePf'],c['rampSeconds'])
        g=groups.setdefault(key,dict(highOhms=key[0],extraCapacitancePf=key[1],rampSeconds=key[2],failedEdgeCaseIndices=[],dataHeadroomSeconds=math.inf,strobeHeadroomSeconds=math.inf))
        if not c['edgePassed']:g['failedEdgeCaseIndices'].append(i)
        for name in ('data','strobe'):g[name+'HeadroomSeconds']=min(g[name+'HeadroomSeconds'],c[name+'HeadroomSeconds'])
    for g in groups.values():
        for name in ('data','strobe'):
            bound=g[name+'HeadroomSeconds']
            g[name+'DelayIntervalSeconds']=[0.,bound] if not g['failedEdgeCaseIndices'] and bound>=0 else None
    return list(groups.values())


def deck(c):
    limits=json.loads((HERE/'bus_switching_limits.json').read_text());load=limits['switchingLoad'];edge=limits[c['kind']]
    drive=f'PWL(0 {c["startDriveVolts"]:.17g} {c["rampSeconds"]:.17g} {c["driveVolts"]:.17g})' if c['rampSeconds'] else f'{c["driveVolts"]:.17g}'
    lines=['I8282 finite drive ramp with final-state resistance',f'Vdrive drive 0 {drive}',
        f'Rdriver drive out {c["resistanceOhms"]:.17g}',f'Vbias bias 0 {load["biasVolts"]:.17g}',
        f'Rload bias out {load["resistanceOhms"]:.17g}',
        f'Cload out 0 {load["capacitanceFarads"]+c["extraCapacitancePf"]*1e-12:.17g} IC={c["initialVolts"]:.17g}',
        '.options reltol=1e-8 abstol=1e-12','.control','tran 0.02n 300n 0 0.02n uic']
    for name,target in (('from',edge['fromVolts']),('to',edge['toVolts']),('propagation',c['measurementVolts'])):
        lines.append(f'meas tran {name}_time WHEN v(out)={target:.17g} {c["kind"].upper()}=1')
    return '\n'.join(lines+['quit','.endc','.end',''])


def evaluate(c,log):
    if solver_diagnostic(log):raise ValueError('Solver diagnostic')
    values={}
    for name,expected in c['crossings'].items():
        matches=re.findall(r'^'+name+r'_time\s*=\s*(\S+)',log,re.M)
        if len(matches)!=1:raise ValueError('Missing unique crossing')
        value=float(matches[0])
        if not math.isfinite(value) or abs(value-expected)>ALLOWANCE:raise ValueError('Analytic/SPICE disagreement')
        values[name]=value
    if ((values['to']-values['from'])<=c['maximumSeconds'])!=c['edgePassed']:raise ValueError('Ambiguous edge classification')
    return values


def verify(out):
    report=json.loads((out/'assessment.json').read_text());rows=list(cases())
    if report['sources']!={n:sha(HERE/n) for n in SOURCES}:raise ValueError('Changed sources')
    if not report['completed'] or report['qualified'] or report['deviceAdmitted']:raise ValueError('Invalid status')
    if len(rows)!=len(report['cases']) or report['jointBudgets']!=budgets(rows):raise ValueError('Changed coverage/budgets')
    for i,(c,a) in enumerate(zip(rows,report['cases'])):
        folder=out/str(i)
        if a['case']!=c or (folder/'probe.cir').read_text()!=deck(c):raise ValueError('Changed conditions')
        if a['files']!={n:sha(folder/n) for n in ('probe.cir','ngspice.log')}:raise ValueError('Changed evidence')
        if a['measuredCrossings']!=evaluate(c,(folder/'ngspice.log').read_text()):raise ValueError('Changed measurement')
    print('Finite I8282 slew constraints verified; device admission remains open.')


def run(out,executable):
    out=out.resolve();out.mkdir(parents=True,exist_ok=False)
    engine=Path(shutil.which(executable) or executable).resolve();runtime=dict(path=str(engine),sha256=sha(engine))
    (out/'spinit').write_text('* Isolated finite drive ramps\n');rows=list(cases())
    report=dict(completed=False,qualified=False,deviceAdmitted=False,runtime=runtime,
        sources={n:sha(HERE/n) for n in SOURCES},jointBudgets=budgets(rows),cases=[],
        scope='Published industrial I8282 78-ohm/2.01-V/300-pF load, three supplies, both polarities, explicit 0/12/30-pF added capacitance and 0/10/30/60-ns internal drive ramps. Pin voltages start at the opposite loaded steady state.',
        assumptions='Resistance switches immediately to its final-state value while the Thevenin source ramps between ground and supply. This can cause a short wrong-direction falling-edge excursion; it is an explicit hypothesis, not a transistor model. Pure data/strobe delay precedes this whole transition. Ramp durations and added capacitance are assumptions.',
        notEstablished=['Actual internal drive shape and resistance transition','Enable measurement convention and dynamics','Finite disconnect dynamics; retain separate instantaneous-disconnect constraints','Nonlinear I/V, temperature law, supply recovery and device/specimen admission'])
    for i,c in enumerate(rows):
        folder=out/str(i);folder.mkdir();(folder/'probe.cir').write_text(deck(c))
        p=subprocess.run([str(engine),'-n','-b','probe.cir'],cwd=folder,env=dict(os.environ,SPICE_SCRIPTS=str(out)),capture_output=True,text=True,timeout=30)
        log=p.stdout+p.stderr;(folder/'ngspice.log').write_text(log);p.check_returncode()
        report['cases'].append(dict(case=c,measuredCrossings=evaluate(c,log),files={n:sha(folder/n) for n in ('probe.cir','ngspice.log')}))
    if sha(engine)!=runtime['sha256']:raise ValueError('Changed runtime')
    report['completed']=True;(out/'assessment.json').write_text(json.dumps(report,indent=2)+'\n');verify(out)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);p.add_argument('--ngspice',default='ngspice');p.add_argument('--verify',action='store_true');a=p.parse_args()
    if a.verify:verify(a.out)
    else:run(a.out,a.ngspice)
