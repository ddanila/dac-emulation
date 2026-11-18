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
    # Shift the knots themselves. Resampling a shifted waveform onto the old
    # grid changes its corners/amplitude and contaminates a phase derivative.
    n=len(values);phase%=1
    x=(-phase*n)%n;j=math.floor(x);f=x-j
    boundary=values[j]*(1-f)+values[(j+1)%n]*f
    knots={0.:boundary,period:boundary}
    for i,value in enumerate(values):
        t=((i/n+phase)%1)*period
        knots[t]=value
    pairs=[]
    for t,value in sorted(knots.items()):pairs.extend((f'{t:.15g}',f'{value:.15g}'))
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


def measurement(raw,period=62.5e-6):
    edges=[];previous=None;integral=0.;span=0.;rows=[]
    for row in steady_supply.raw_rows(raw):
        rows.append(row)
        if previous:
            dt=row['time']-previous['time']
            integral+=dt*(row['v(h_control)']+previous['v(h_control)'])/2;span+=dt
            if previous['v(h_drivecol)']<10<=row['v(h_drivecol)']:
                edges.append(previous['time']+dt*(10-previous['v(h_drivecol)'])/(row['v(h_drivecol)']-previous['v(h_drivecol)']))
        previous=row
    if previous is None or abs(previous['time']-.005)>1e-12 or not span:raise ValueError('incomplete perturbation trace')
    times=[r['time'] for r in rows]
    def sample(t,key):
        j=bisect.bisect_right(times,t);j=min(max(j,1),len(rows)-1)
        a,b=rows[j-1],rows[j];f=(t-a['time'])/(b['time']-a['time'])
        return a[key]+f*(b[key]-a[key])
    # Before the perturbation, compare the last eight autonomous oscillator
    # cycles by phase, and the forced control ripple by its own input period.
    pre=[t for t in edges if t<.0035]
    errors={}
    if len(pre)<10:errors['missing_pre_pulse_cycles']=1.
    else:
        intervals=[b-a for a,b in zip(pre[-10:],pre[-9:])]
        errors['period']=(max(intervals)-min(intervals))/max(intervals)
        waves=[[sample(a+(b-a)*i/128,'v(h_drivecol)') for i in range(128)]
               for a,b in zip(pre[-9:-1],pre[-8:])]
        errors['oscillator']=max(math.sqrt(sum((a-b)**2 for a,b in zip(w,waves[-1]))/max(sum(b*b for b in waves[-1]),1e-30)) for w in waves[:-1])
    waves=[[sample(.0035-(8-k)*period+i*period/128,'v(h_control)') for i in range(128)] for k in range(8)]
    errors['control']=max(math.sqrt(sum((a-b)**2 for a,b in zip(w,waves[-1]))/max(sum(b*b for b in waves[-1]),1e-30)) for w in waves[:-1])
    return dict(mean_control_v=integral/span,edges_s=edges,settling_relative_errors=errors,
                settled=all(math.isfinite(v) and v<.01 for v in errors.values()))


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
    def trial(name,*,delta=None,phase=None,step_ns=25):
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
        deck=deck.replace('.tran 100n 5m 3m 100n',f'.tran {step_ns}n 5m 2.5m {step_ns}n')
        deck=deck.replace('reltol=.0001',f'reltol={.0001*step_ns/100:.12g}')
        folder=out/name;solved=steady_supply.solve(deck,folder,runtime,timeout_s=deadline-time.monotonic())
        entry=dict(solve=solved,delta_v=delta,feedback_phase_lines=phase,step_ns=step_ns)
        report['trials'][name]=entry;save()
        if solved['status']!='complete':raise ValueError('isolation solver failed: '+name)
        entry['measurement']=measurement(folder/'trace.raw',period);save();return entry['measurement']
    save()
    try:
        # A Cartesian cross: vary amplitude at fixed fine resolution, then
        # resolution at fixed smallest amplitude. Do not conflate the two.
        osc={};base={};all_settled=True
        for step in (100,50,25):
            base[step]=trial(f'control-zero-{step}',delta=0,step_ns=step)
            all_settled &= base[step]['settled']
            for amplitude in ((.05,.025,.0125) if step==25 else (.0125,)):
                minus=trial(f'control-minus-{step}-{amplitude}',delta=-amplitude,step_ns=step)
                plus=trial(f'control-plus-{step}-{amplitude}',delta=amplitude,step_ns=step)
                all_settled &= minus['settled'] and plus['settled']
                osc[step,amplitude]=pulse_response(base[step],minus,plus,period,amplitude)
        def convergence(values):
            comparisons=[refined_sign(a,b) for a,b in zip(values,values[1:])]
            return dict(values=values,comparisons=comparisons,verified=all(c['verified'] for c in comparisons))
        response=osc[25,.0125]
        report['oscillator_lines_per_v']=response
        report['oscillator_refinement']=dict(
            amplitude=convergence([osc[25,a] for a in (.05,.025,.0125)]),
            solver=convergence([osc[s,.0125] for s in (100,50,25)]),settled=all_settled)
        report['oscillator_refinement']['verified']=all_settled and all(report['oscillator_refinement'][k]['verified'] for k in ('amplitude','solver'));save()
        for phase in (.125,.375,.625,.875):
            slopes={};settled=True
            for step in (100,50,25):
                for amplitude in ((.005,.0025,.00125) if step==25 else (.00125,)):
                    low=trial(f'phase-{phase}-minus-{step}-{amplitude}',phase=phase-amplitude,step_ns=step)
                    high=trial(f'phase-{phase}-plus-{step}-{amplitude}',phase=phase+amplitude,step_ns=step)
                    slopes[step,amplitude]=(high['mean_control_v']-low['mean_control_v'])/(2*amplitude)
                    settled &= low['settled'] and high['settled']
            refinement=dict(amplitude=convergence([slopes[25,a] for a in (.005,.0025,.00125)]),
                            solver=convergence([slopes[s,.00125] for s in (100,50,25)]),settled=settled)
            refinement['verified']=settled and all(refinement[k]['verified'] for k in ('amplitude','solver'))
            report['screens'].append(dict(phase_lines=phase,**correction(slopes[25,.00125],response),
                detector_refinement=refinement,screen_usable=refinement['verified'] and report['oscillator_refinement']['verified']));save()
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
