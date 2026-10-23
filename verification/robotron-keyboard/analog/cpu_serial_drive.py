#!/usr/bin/env python3
"""Screen CPU D0/WR drive hypotheses against endpoints and the 7406 candidate.

Supply-anchored resistance satisfies the published high test point throughout
its supply range. It is a diagnostic interpolation, not an identified I/V law.
"""
import argparse
import json
import lzma
import math
import os
from pathlib import Path
import shutil

from gate_switching_probe import sha
from prepare_dynamic_driver import checked_candidate
from ttl7406_dynamic import run

HERE=Path(__file__).resolve().parent


def high_resistance(supply, profile, anchored):
    if not math.isfinite(supply) or not 4.75 <= supply <= 5.25:
        raise ValueError('CPU supply outside the reviewed range')
    high=profile['outputHigh']
    return ((supply if anchored else 5)-high['minimumVolts'])/high['sourceMagnitudeAmps']


def endpoint(supply,profile,anchored):
    high=profile['outputHigh'];r=high_resistance(supply,profile,anchored)
    v=supply-r*high['sourceMagnitudeAmps']
    return dict(supplyV=supply,highOhms=r,loadedHighV=v,
                passed=v>=high['minimumVolts']-1e-12)


def first_crossing(rows,column,threshold,rising,start,end):
    for a,b in zip(rows,rows[1:]):
        if a[0]<start or b[0]>end:continue
        crosses = a[column]<threshold<=b[column] if rising else a[column]>threshold>=b[column]
        if crosses:
            return [a[0],b[0]]
    raise ValueError('Missing threshold crossing')


def probe(folder,executable,env,candidate,profile,supply,temp,cap,anchored,step):
    high=high_resistance(supply,profile,anchored)
    low=profile['outputLow']['maximumVolts']/profile['outputLow']['sinkAmps']
    rows=run(folder,executable,env,candidate,f'''
.temp {temp}
Vcc vp 0 {supply}
Venable en 0 PWL(0 0 200n 0 201n 1 1200n 1 1201n 0 2u 0)
Bhigh vp a I=(V(vp)-V(a))*V(en)/{high:.17g}
Blow a 0 I=V(a)*(1-V(en))/{low:.17g}
Cpin a 0 {cap}p
Xdut a y vp 0 TTL7406_DYNAMIC
Rpull vp y 560
Cload y 0 1000p
.save all @bhigh[i] @blow[i]
''',f'tran {step}n 2u 0 {step}n','v(a) v(y) @bhigh[i] @blow[i]')
    high_at=min(rows,key=lambda r:abs(r[0]-1190e-9))
    low_at=rows[-1]
    rising=first_crossing(rows,1,2,True,200e-9,1200e-9)
    falling=first_crossing(rows,1,.8,False,1200e-9,2e-6)
    output=first_crossing(rows,2,.8,False,200e-9,1200e-9)
    info=dict(supplyV=supply,temperatureC=temp,pinPf=cap,anchored=anchored,stepNs=step,
        inputHighV=high_at[1],inputLowV=low_at[1],
        highMarginV=high_at[1]-2,lowMarginV=.8-low_at[1],
        levelsPass=high_at[1]>=2 and low_at[1]<=.8,
        inputRiseDelayNs=[(t-200e-9)*1e9 for t in rising],
        inputFallDelayNs=[(t-1200e-9)*1e9 for t in falling],
        sourceToOutputLowNs=[(t-200e-9)*1e9 for t in output],
        maximumSourceA=max(r[3] for r in rows),maximumSinkA=max(r[4] for r in rows))
    p=folder/'trace.txt';(folder/'trace.txt.xz').write_bytes(lzma.compress(p.read_bytes()));p.unlink()
    return info


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--device-report',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--ngspice',default='ngspice')
    a=p.parse_args();a.out=a.out.resolve();a.out.mkdir(parents=True,exist_ok=False)
    executable=Path(shutil.which(a.ngspice) or a.ngspice).resolve()
    (a.out/'spinit').write_text('* CPU drive diagnostic.\n')
    env=dict(os.environ,SPICE_SCRIPTS=str(a.out))
    candidate=checked_candidate(json.loads(a.device_report.read_text()),0)
    limits=json.loads((HERE/'bus_limits.json').read_text())
    profile=limits['profiles']['U880']
    gate=limits['profiles']['7406']
    report=dict(completed=False,qualified=False,boardAdmission=False,
        sources={n:sha(HERE/n) for n in ('cpu_serial_drive.py','bus_limits.json','ttl7406_dynamic.py','prepare_dynamic_driver.py','gate_switching_probe.py','failure_evidence.py')},
        deviceReportSha256=sha(a.device_report),executableSha256=sha(executable),
        endpoints={str(anchored):[endpoint(v,profile,anchored) for v in (4.75,5,5.25)] for anchored in (False,True)},
        staticSingleGateHeadroom=dict(
            highCurrentA=profile['outputHigh']['sourceMagnitudeAmps']-gate['inputHighCurrent']['maximumAmps'],
            lowCurrentA=profile['outputLow']['sinkAmps']+gate['inputLowCurrent']['minimumAmps'],
            scope='Published endpoint comparison for one SN7406 input only; not total bus fanout or transient current.'),
        runs=[],
        boundary='Fixed resistance is the retained control. Supply-anchored resistance satisfies one published DC endpoint, not device dynamics. 10/34 pF are existing WR/D0 fixture loads, not measured bounds. Temperature varies the candidate gate only; CPU temperature, leakage, bus contention, supply transients and cable/filter recovery are not modeled here.')
    try:
        for anchored in (False,True):
            for supply in (4.75,5,5.25):
                for temp in (0,25,70):
                    for cap in (10,34):
                        report['runs'].append(probe(a.out/f'run-{len(report["runs"]):03}',executable,env,candidate,profile,supply,temp,cap,anchored,.5))
        worst=max(report['runs'],key=lambda r:r['sourceToOutputLowNs'][1])
        report['limitingCaseRefinement']=[worst]+[probe(a.out/f'refine-{step}',executable,env,candidate,profile,worst['supplyV'],worst['temperatureC'],worst['pinPf'],worst['anchored'],step) for step in (.25,.125)]
        report['completed']=True
    except Exception as error:
        report['error']=str(error)
        raise
    finally:
        report['artifacts']={str(f.relative_to(a.out)):sha(f) for f in sorted(a.out.rglob('*')) if f.is_file() and f.name!='report.json'}
        (a.out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(a.out/'report.json')


if __name__=='__main__':main()
