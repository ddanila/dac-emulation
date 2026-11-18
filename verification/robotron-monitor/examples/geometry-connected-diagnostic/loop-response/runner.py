#!/usr/bin/env python3
"""Small-perturbation isolation screen retaining recorded control ripple.

Positive phase means later feedback/oscillator edges. This reports local stage
response signs, not connected-loop stability or a calibrated loop transfer model.
"""
import argparse
import bisect
from collections import deque
import hashlib
import json
import math
from pathlib import Path
import time
import horizontal_isolation as isolation
import steady_supply


def wave(values,period,phase=0):
    n=len(values);pairs=[]
    for i in range(n+1):
        x=(i-phase*n)%n;j=math.floor(x);f=x-j
        value=values[j]*(1-f)+values[(j+1)%n]*f
        pairs.extend((f'{i*period/n:.15g}',f'{value:.15g}'))
    return 'PWL('+' '.join(pairs)+') r=0'


def control_cycle(trace,stimulus):
    window=deque()
    for row in steady_supply.raw_rows(trace):
        window.append(row)
        while len(window)>2 and window[1]['time']<row['time']-.001:window.popleft()
    rows=list(window)
    edges=[]
    for a,b in zip(rows,rows[1:]):
        if a['v(h_hot)']<150<=b['v(h_hot)']:
            edges.append(a['time']+(b['time']-a['time'])*(150-a['v(h_hot)'])/(b['v(h_hot)']-a['v(h_hot)']))
    if len(edges)<2:raise ValueError('missing control cycle')
    start,end=edges[-2:];times=[r['time'] for r in rows];values=[]
    for i in range(256):
        t=start+(end-start)*i/256;j=bisect.bisect_right(times,t)
        a,b=rows[j-1],rows[j];f=(t-a['time'])/(b['time']-a['time'])
        values.append(a['v(h_control)']+f*(b['v(h_control)']-a['v(h_control)']))
    return values


def measurement(raw):
    edges=[];previous=None;integral=0.;span=0.
    for row in steady_supply.raw_rows(raw):
        if previous:
            dt=row['time']-previous['time']
            integral+=dt*(row['v(h_control)']+previous['v(h_control)'])/2;span+=dt
            if previous['v(h_drivecol)']<10<=row['v(h_drivecol)']:
                edges.append(previous['time']+dt*(10-previous['v(h_drivecol)'])/(row['v(h_drivecol)']-previous['v(h_drivecol)']))
        previous=row
    if previous is None or abs(previous['time']-.005)>1e-12 or not span:raise ValueError('incomplete perturbation trace')
    return dict(mean_control_v=integral/span,edges_s=edges)


def correction(detector_v_per_line,oscillator_lines_per_v):
    product=detector_v_per_line*oscillator_lines_per_v
    return dict(detector_v_per_line=detector_v_per_line,oscillator_lines_per_v=oscillator_lines_per_v,
        sign_product=product,corrective=product<0,
        qualification='local-isolation-response-sign-only',connected_lock_verified=False)


def pulse_response(base,minus,plus,period,amplitude):
    if len({len(r['edges_s']) for r in (base,minus,plus)})!=1:
        raise ValueError('pulse changed edge count; local phase response not comparable')
    indexes=[i for i,t in enumerate(base['edges_s']) if .0035+period<t<.0035+5*period]
    pre=[i for i,t in enumerate(base['edges_s']) if t<.0035]
    if not indexes or not pre:raise ValueError('missing before/after pulse edges')
    if max(abs(r['edges_s'][i]-base['edges_s'][i]) for r in (minus,plus) for i in pre)>1e-9:
        raise ValueError('perturbations changed the pre-pulse state')
    return sum((plus['edges_s'][i]-minus['edges_s'][i])/(period*2*amplitude) for i in indexes)/len(indexes)


def refined_sign(coarse,fine):
    scale=max(abs(coarse),abs(fine),1e-12)
    error=abs(coarse-fine)/scale
    return dict(relative_change=error,verified=coarse*fine>0 and error<.01)


def run(trace,output,runtime,*,tank_h=.00145,seconds=600):
    out=Path(output).resolve();out.mkdir(parents=True,exist_ok=False)
    (out/'runner.py').write_bytes(Path(__file__).read_bytes())
    stimulus=isolation.recorded_cycles(trace);stimulus['control_ripple_v']=control_cycle(trace,stimulus)
    (out/'stimulus.json').write_text(json.dumps(stimulus,indent=2)+'\n')
    period=stimulus['isolation_period_s'];deadline=time.monotonic()+seconds
    report=dict(format='dac-local-loop-response-v1',status='incomplete',trials={},screens=[],
        connected_lock_verified=False,full_monitor_qualified=False,
        stimulus_sha256=hashlib.sha256((out/'stimulus.json').read_bytes()).hexdigest(),
        qualifications=['Retimed measured cycle shapes; dummy driver secondary load.',
          'Finite pulse response is not a DC tuning slope or full loop transfer function.'])
    def save():(out/'response.json').write_text(json.dumps(report,indent=2)+'\n')
    def trial(name,*,delta=None,phase=None,fine=False):
        if time.monotonic()>=deadline:raise TimeoutError('isolation wall budget exhausted')
        deck,meta=isolation.make_deck({'horizontal_tank_l':tank_h},0)
        deck=deck.replace('.save time v(h_drivecol) v(h_control) i(Vcontrol)', '.save time v(h_drivecol) v(h_control)')
        if delta is not None:
            deck=deck.replace('Vcontrol h_control 0 0',
                'Vripple ripple 0 '+wave(stimulus['control_ripple_v'],period)+'\n'+
                f'Voffset offset 0 PWL(0 0 3.5m 0 3.50001m {delta} {(.0035+period):.15g} {delta} {(.00350001+period):.15g} 0)\n'+
                'Bforced h_control 0 V={v(ripple)+v(offset)}')
        else:
            deck=deck.replace('Vcontrol h_control 0 0\n','')
            for key,node in (('sync','sync_c'),('feedback','h_feedback')):
                deck=deck.replace(f'V{key} {node} 0 0',f'V{key} {node} 0 '+wave(stimulus['waveforms'][key],period,phase if key=='feedback' else 0))
        if fine:deck=deck.replace('.tran 100n 5m 3m 100n','.tran 50n 5m 3m 50n')
        folder=out/name;solved=steady_supply.solve(deck,folder,runtime,timeout_s=deadline-time.monotonic())
        entry=dict(solve=solved,delta_v=delta,feedback_phase_lines=phase)
        report['trials'][name]=entry;save()
        if solved['status']!='complete':raise ValueError('isolation solver failed: '+name)
        entry['measurement']=measurement(folder/'trace.raw');save();return entry['measurement']
    save()
    try:
        base=trial('control-zero',delta=0)
        minus=trial('control-minus',delta=-.05);plus=trial('control-plus',delta=.05)
        response=pulse_response(base,minus,plus,period,.05)
        fine_base=trial('control-fine-zero',delta=0,fine=True)
        fine_minus=trial('control-fine-minus',delta=-.025,fine=True)
        fine_plus=trial('control-fine-plus',delta=.025,fine=True)
        fine_response=pulse_response(fine_base,fine_minus,fine_plus,period,.025)
        report['oscillator_lines_per_v']=response
        report['oscillator_refinement']=dict(coarse=response,fine=fine_response,**refined_sign(response,fine_response));save()
        for phase in (.125,.375,.625,.875):
            low=trial(f'phase-{phase}-minus',phase=phase-.005)
            high=trial(f'phase-{phase}-plus',phase=phase+.005)
            slope=(high['mean_control_v']-low['mean_control_v'])/.01
            fine_low=trial(f'phase-{phase}-fine-minus',phase=phase-.0025,fine=True)
            fine_high=trial(f'phase-{phase}-fine-plus',phase=phase+.0025,fine=True)
            fine_slope=(fine_high['mean_control_v']-fine_low['mean_control_v'])/.005
            refinement=refined_sign(slope,fine_slope)
            usable=refinement['verified'] and report['oscillator_refinement']['verified']
            report['screens'].append(dict(phase_lines=phase,**correction(slope,response),
                detector_refinement=refinement,screen_usable=usable));save()
        report['status']='complete'
    except (ValueError,TimeoutError) as error:
        report.update(status='blocked',reason=str(error))
    save();return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('trace','output','runtime'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--tank-h',type=float,default=.00145)
    a=p.parse_args();result=run(a.trace,a.output,a.runtime,tank_h=a.tank_h)
    print(json.dumps(result,indent=2));raise SystemExit(0 if result['status']=='complete' else 2)
