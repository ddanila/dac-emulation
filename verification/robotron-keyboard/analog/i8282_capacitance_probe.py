#!/usr/bin/env python3
"""Test joint resistance/capacitance hypotheses under the published I8282 load."""
import argparse
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
from bus_switching_probe import duration, measurement, ALLOWANCE
from i8282_enabled_candidates import cases as enabled_cases, deck as enabled_deck, SOURCES as BASE_SOURCES
from ttl7406_probe import sha

HERE=Path(__file__).resolve().parent
SOURCES=('i8282_capacitance_probe.py','bus_cosim.py',*BASE_SOURCES)
EXTRA_PF=(0.,12.,30.)


def cases():
    limits=json.loads((HERE/'bus_switching_limits.json').read_text())
    for c in enabled_cases():
        if c['kind'] not in ('rise','fall'):continue
        for extra in EXTRA_PF:
            spec=limits[c['kind']];load=dict(limits['switchingLoad'])
            load['capacitanceFarads']+=extra*1e-12
            expected=duration(c['driveVolts'],c['resistanceOhms'],load,spec['fromVolts'],spec['toVolts'])
            yield dict(c,extraCapacitancePf=extra,expectedSeconds=expected,
                       withinPublishedLimit=expected<=c['maximumSeconds'])


def budgets():
    groups={}
    load_pf=json.loads((HERE/'bus_switching_limits.json').read_text())['switchingLoad']['capacitanceFarads']*1e12
    for c in enabled_cases():
        if c['kind'] not in ('rise','fall'):continue
        key=(c['highOhms'],c['supplyVolts'])
        groups.setdefault(key,{})[c['kind']]=load_pf*(c['maximumSeconds']/c['expectedSeconds']-1)
    return [{'highOhms':r,'supplyVolts':v,'edgeExtraCapacitanceBoundsPf':bounds,
             'maximumExtraCapacitancePf':min(bounds.values())} for (r,v),bounds in groups.items()]


def deck(case):
    # CL stays exactly the published external load. Added device capacitance is
    # a separate hypothesis, never substituted for CL or inferred from CIN.
    return enabled_deck(case).replace('.options reltol=',
        f'Cdevice out 0 {case["extraCapacitancePf"]*1e-12:.17g}\n.options reltol=') if case['extraCapacitancePf'] else enabled_deck(case)


def verify(out):
    r=json.loads((out/'assessment.json').read_text())
    if r.get('completed') is not True or r.get('qualified') is not False or r.get('deviceAdmitted') is not False:raise ValueError('Invalid qualification status')
    if r['sources']!={n:sha(HERE/n) for n in SOURCES}:raise ValueError('Stale sources')
    expected=list(cases())
    if len(r['cases'])!=len(expected):raise ValueError('Missing cases')
    for i,(c,actual) in enumerate(zip(expected,r['cases'])):
        folder=out/str(i)
        if actual['case']!=c or (folder/'probe.cir').read_text()!=deck(c):raise ValueError('Changed conditions')
        if actual['files']!={n:sha(folder/n) for n in ('probe.cir','ngspice.log')}:raise ValueError('Changed evidence')
        measured=measurement((folder/'ngspice.log').read_text())
        if measured!=actual['measuredSeconds'] or abs(measured-c['expectedSeconds'])>ALLOWANCE:raise ValueError('Invalid RC measurement')
        if (measured<=c['maximumSeconds'])!=c['withinPublishedLimit']:raise ValueError('Ambiguous measured result')
    expected_budgets=budgets()
    if len(r['capacitanceBudgets'])!=len(expected_budgets):raise ValueError('Missing budgets')
    for a,b in zip(r['capacitanceBudgets'],expected_budgets):
        if any(a[k]!=b[k] for k in ('highOhms','supplyVolts')):raise ValueError('Changed budget condition')
        if not math.isclose(a['maximumExtraCapacitancePf'],b['maximumExtraCapacitancePf'],rel_tol=1e-12):raise ValueError('Changed capacitance budget')
        if set(a['edgeExtraCapacitanceBoundsPf'])!={'rise','fall'}:raise ValueError('Missing edge budget')
        for edge in ('rise','fall'):
            if not math.isclose(a['edgeExtraCapacitanceBoundsPf'][edge],b['edgeExtraCapacitanceBoundsPf'][edge],rel_tol=1e-12):raise ValueError('Changed edge budget')
    print('Joint I8282 resistance/capacitance constraints verified; device admission remains open.')


def run(out,executable):
    out=out.resolve();out.mkdir(parents=True,exist_ok=False)
    engine=Path(shutil.which(executable) or executable).resolve();runtime={'path':str(engine),'sha256':sha(engine)}
    (out/'spinit').write_text('* Joint enabled-output hypothesis test\n')
    r={'completed':False,'qualified':False,'deviceAdmitted':False,'runtime':runtime,
       'scope':'Published 300-pF external load plus explicitly assumed device capacitance; instantaneous linear drive, no internal switching delay.',
       'extraCapacitanceScope':'0 pF is the prior fastest-response control; 12 pF is the existing bus_cosim fixture assumption, not an I8282 output specification; 30 pF is a sensitivity hypothesis.',
       'decision':'The 250-ohm high-side candidate with the existing 12-pF assumption fails the minimum-supply rise limit. Do not combine those choices in an admitted model. The 125-ohm candidate passes these tested capacitances but remains a non-unique hypothesis.',
       'boundScope':'Necessary total extra-capacitance ceilings within the constant-resistance family, computed from both edge limits. These are not measured capacitance values or a bound on nonlinear transistor models.',
       'capacitanceBudgets':budgets(),'sources':{n:sha(HERE/n) for n in SOURCES},'cases':[]}
    for i,c in enumerate(cases()):
        folder=out/str(i);folder.mkdir();(folder/'probe.cir').write_text(deck(c))
        p=subprocess.run([str(engine),'-n','-b','probe.cir'],cwd=folder,env=dict(os.environ,SPICE_SCRIPTS=str(out)),capture_output=True,text=True,timeout=30)
        log=p.stdout+p.stderr;(folder/'ngspice.log').write_text(log);p.check_returncode();value=measurement(log)
        if abs(value-c['expectedSeconds'])>ALLOWANCE:raise ValueError('RC measurement mismatch')
        r['cases'].append({'case':c,'measuredSeconds':value,'files':{n:sha(folder/n) for n in ('probe.cir','ngspice.log')}})
    if sha(engine)!=runtime['sha256']:raise ValueError('Changed runtime')
    r['completed']=True;(out/'assessment.json').write_text(json.dumps(r,indent=2)+'\n');verify(out)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--ngspice',default='ngspice');p.add_argument('--verify',action='store_true');a=p.parse_args()
    if a.verify:verify(a.out)
    else:run(a.out,a.ngspice)
