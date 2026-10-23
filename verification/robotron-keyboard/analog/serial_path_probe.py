#!/usr/bin/env python3
"""Replay a retained serial excursion with internal device and energy observations.

Recorded input, supply and cable ground are imposed boundaries, not feedback.
Prelude and step controls test the isolated replay, not full-board admission.
"""
import argparse
from functools import lru_cache
import json
import lzma
import os
import re
from pathlib import Path
import shutil

from analog_driver_replay import reduce_linear
from gate_switching_probe import sha
from network_trace import PHYSICAL_SIGNALS
from prepare_dynamic_driver import checked_candidate
from ttl7406_dynamic import run

HERE = Path(__file__).resolve().parent
SIGNALS = ['v(a)', 'v(y)', 'v(cable)', 'v(cable,cable_g)', 'v(vp)', 'v(cable_g)',
           'i(Lfilter)', 'v(xdut.output_base)',
           *[f'@q.xdut.qoutput[{s}]' for s in ('ic','ib','vbc','vbe','qbc','qbe')],
           'i(Vinput)', 'i(Vcc)']


def samples(path):
    with lzma.open(path, 'rt') as stream:
        if next(stream).split() != ['time', *PHYSICAL_SIGNALS]:
            raise ValueError('Unexpected physical trace')
        for line in stream:
            row = list(map(float, line.split()))
            if len(row) != len(PHYSICAL_SIGNALS)+1:
                raise ValueError('Invalid row')
            yield row


def interpolate(rows, time, column):
    lo,hi=0,len(rows)
    while lo<hi:
        mid=(lo+hi)//2
        if rows[mid][0]<time:lo=mid+1
        else:hi=mid
    i=lo
    if i == 0: return rows[0][column]
    if i == len(rows): return rows[-1][column]
    a,b = rows[i-1:i+1]
    return a[column]+(b[column]-a[column])*(time-a[0])/(b[0]-a[0])


@lru_cache(maxsize=16)
def pwl(name, node, rows, column, start, stop):
    knots = [(start, interpolate(rows,start,column))]
    knots += [(r[0],r[column]) for r in rows if start < r[0] < stop]
    knots += [(stop, interpolate(rows,stop,column))]
    knots=reduce_linear(knots,1e-7)
    return f'{name} {node} 0 PWL(\n'+'\n'.join(f'+ {t-start:.17g} {v:.17g}' for t,v in knots)+'\n+ )'


def replay(out, executable, env, candidate, rows, event, prelude, step, cap=1000, inductance=1, moving_ground=True):
    start,stop=event-prelude*1e-6,event+1e-6
    circuit='\n'.join([pwl('Vinput','a',rows,16,start,stop),
        pwl('Vcc','vp',rows,1,start,stop),
        pwl('Vground','cable_g',rows,9,start,stop) if moving_ground else 'Vground cable_g 0 0',
        'Xdut a y vp 0 TTL7406_DYNAMIC', 'Rpull vp y 560',
        f'Lfilter y series {inductance}u', 'Rfilter series cable 1',
        f'Cload cable cable_g {cap}p', 'Rload cable cable_g 100k',
        '.temp 27', '.options trtol=1 minbreak=1f', '.save all '+' '.join(SIGNALS)])
    trace=run(out,executable,env,candidate,circuit,
              f'tran {step}n {stop-start:.17g} 0 {step}n',' '.join(SIGNALS))
    if abs(trace[-1][0]-(stop-start))>1e-15:raise ValueError('Incomplete replay')
    window=[r for r in trace if event-.5e-6 <= r[0]+start <= stop]
    worst=min(window,key=lambda r:r[2])
    mismatch=max(abs(r[2]-interpolate(rows,r[0]+start,3)) for r in window)
    info=dict(completed=True,preludeUs=prelude,stepNs=step,loadPf=cap,inductanceUh=inductance,
        movingGround=moving_ground,absoluteStartSeconds=start,
        minimumOutputV=worst[2],minimumReceiverV=min(r[4] for r in window),
        absoluteMinimumTimeSeconds=worst[0]+start,
        peakDifferenceFromLiveOutputV=mismatch,
        atMinimum=dict(zip(SIGNALS,worst[1:])),
        maximumForwardBaseCollectorV=max(r[11] for r in window),
        peakInductorEnergyJ=max(.5*inductance*1e-6*r[7]**2 for r in window),
        peakLoadEnergyJ=max(.5*cap*1e-12*r[4]**2 for r in window),
        baseCollectorChargeRangeC=[min(r[13] for r in window),max(r[13] for r in window)],
        peakCollectorCurrentA=max(abs(r[9]) for r in window))
    # Retain every accepted point; compressed traces are sufficient to recompute metrics.
    p=out/'trace.txt';(out/'trace.txt.xz').write_bytes(lzma.compress(p.read_bytes()));p.unlink()
    return info


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--live',type=Path,required=True)
    p.add_argument('--device-report',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--ngspice',required=True)
    a=p.parse_args();a.out=a.out.resolve();a.out.mkdir(parents=True,exist_ok=False)
    executable=Path(shutil.which(a.ngspice) or a.ngspice).resolve()
    (a.out/'spinit').write_text('* Isolated serial-path replay.\n')
    env=dict(os.environ,SPICE_SCRIPTS=str(a.out), ROBOTRON_MPFR_BITS='256',
             ROBOTRON_MPFR_TRANSITION_ONLY='1',ROBOTRON_MPFR_START='0',
             ROBOTRON_CAP_ASSEMBLY='exact',ROBOTRON_POSTCAP_ASSEMBLY='exact')
    device=json.loads(a.device_report.read_text())
    candidate=checked_candidate(device,0)
    deck_path=a.live.with_name('io.cir')
    deck=deck_path.read_text()
    for expected in ('R10.2 n_p5V n_TA_DATEN 560',
                     'L1.4 n_TA_DATEN L1_4_series 1u',
                     'RL1.4 L1_4_series n_CABLE_DATEN 1',
                     'Cdata_load n_CABLE_DATEN n_CABLE_GND 1000p',
                     'Rdata_load n_CABLE_DATEN n_CABLE_GND 100k',
                     'Xdata n_D0 n_TA_DATEN driver_vp 0 TTL7406_DYNAMIC',
                     'Vdriver_supply n_p5V driver_vp 0'):
        if deck.splitlines().count(expected)!=1:raise ValueError('Changed source circuit: '+expected)
    if candidate not in deck or re.search(r'^\.temp ',deck,re.M):
        raise ValueError('Changed source candidate or temperature')
    worst=min(samples(a.live),key=lambda r:r[3]);event=worst[0]
    rows=tuple(tuple(r) for r in samples(a.live) if event-9e-6 <= r[0] <= event+2e-6)
    if not rows or rows[0][0]>event-8e-6 or rows[-1][0]<event+1e-6:
        raise ValueError('Insufficient context')
    report=dict(completed=False,qualified=False,boardAdmission=False,
        sources={n:sha(HERE/n) for n in ('serial_path_probe.py','analog_driver_replay.py','network_trace.py','prepare_dynamic_driver.py','ttl7406_dynamic.py','gate_switching_probe.py','failure_evidence.py')},liveSha256=sha(a.live),
        sourceDeckSha256=sha(deck_path),
        numericEnvironment={k:v for k,v in env.items() if k.startswith('ROBOTRON_')},
        deviceReportSha256=sha(a.device_report),executableSha256=sha(executable),
        liveMinimum=dict(zip(['time',*PHYSICAL_SIGNALS],worst)),runs={},
        sourceInterpolationBudgetV=1e-7, temperatureC=27,
        boundary='Forced recorded D0, board supply and cable ground; no CPU/ground feedback. Controls alter one unqualified load/filter assumption at a time. No fitted clamp, capacitance or recovery parameter is admitted.')
    try:
        for name,prelude,step,cap,inductance,ground in [
            ('control',2,.5,1000,1,True),('long-prelude',4,.5,1000,1,True),
            ('extended-prelude',8,.5,1000,1,True),
            ('half-step',4,.25,1000,1,True),('quarter-step',4,.125,1000,1,True),
            ('small-inductance',4,.25,1000,.001,True),
            ('fixed-ground',4,.25,1000,1,False),
            ('load-100pf',4,.25,100,1,True),('load-15pf',4,.25,15,1,True)]:
            try:
                report['runs'][name]=replay(a.out/name,executable,env,candidate,rows,event,prelude,step,cap,inductance,ground)
            except (ValueError,TimeoutError) as error:
                report['runs'][name]=dict(completed=False,error=str(error),preludeUs=prelude,stepNs=step)
                trace=a.out/name/'trace.txt'
                if trace.exists():
                    trace.with_suffix('.txt.xz').write_bytes(lzma.compress(trace.read_bytes()));trace.unlink()
        alternative=checked_candidate(device,1)
        for name,step in [('junction-2pf',.5),('junction-2pf-half',.25)]:
            try:
                report['runs'][name]=replay(a.out/name,executable,env,alternative,rows,event,4,step)
                report['runs'][name]['alternativeParameters']=device['cases'][1]['parameters']
            except (ValueError,TimeoutError) as error:
                report['runs'][name]=dict(completed=False,error=str(error),stepNs=step)
        report['allRunsCompleted']=all(r['completed'] for r in report['runs'].values())
        report['completed']=True
    except Exception as error:
        report['error']=str(error)
        raise
    finally:
        report['artifacts']={str(f.relative_to(a.out)):sha(f) for f in sorted(a.out.rglob('*')) if f.is_file() and f.name!='report.json'}
        (a.out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(a.out/'report.json')


if __name__=='__main__':main()
