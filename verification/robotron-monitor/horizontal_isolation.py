#!/usr/bin/env python3
"""Source-addressed horizontal tuning isolation bench, never monitor acceptance.

Force the phase-detector control node to measure oscillator tuning direction and
range. This intentionally breaks the loop; results cannot establish sync lock.
The source circuit and chosen parameter values are archived with every solve.
"""
import argparse
import bisect
from collections import deque
from file_hash import digest_stream
import json
from pathlib import Path
import statistics
import time
import lab
import reference
import steady_supply

ROOT=Path(__file__).resolve().parent


def make_deck(parameters,control_v):
    if not -10<=control_v<=25:raise ValueError('control voltage outside isolation bounds')
    profile=reference.read_profile(ROOT/'profiles/k7222-11-horizontal-oscillator.json')
    values=reference.parameter_values(profile,parameters)
    source=(ROOT/'reference/k7222-11/horizontal-transcription.json').read_bytes()
    components=json.loads(source)['components']
    models=(ROOT/'circuits/k7222-11-horizontal-models.cir').read_text()
    lines=['Forced control isolation bench; NOT a connected monitor']
    lines += [f'.param {k}={v:.15g}' for k,v in values.items()]
    lines += [' '.join([p['reference'],*p['nodes'],p['value']]) for p in components]
    lines += [models, 'V12 p12 0 12', 'V22 p22 0 22', 'Vsync sync_c 0 0',
              'Vfeedback h_feedback 0 0', 'Rsecondary h_outputbase 0 1000',
              f'Vcontrol h_control 0 {control_v:.15g}',
              '.options reltol=.0001 abstol=1e-12 vntol=1e-8 method=gear',
              '.save time v(h_drivecol) v(h_control) i(Vcontrol)',
              '.tran 100n 5m 3m 100n', '.end']
    return '\n'.join(lines)+'\n',dict(parameters=values,source_sha256=lab.digest(source),
        models_sha256=lab.digest(models.encode()),control_voltage_v=control_v,
        qualification='forced-control-isolation',full_monitor_qualified=False)


def summarize(path):
    previous=None;edges=[];low=None;high=None;current_j=0.;span=0.
    for row in steady_supply.raw_rows(path):
        value=row['v(h_drivecol)'];low=value if low is None else min(low,value)
        high=value if high is None else max(high,value)
        if previous is not None:
            dt=row['time']-previous['time']
            current_j+=dt*(row['i(vcontrol)']+previous['i(vcontrol)'])/2;span+=dt
            if previous['v(h_drivecol)']<10<=value:
                edges.append(previous['time']+dt*(10-previous['v(h_drivecol)'])/(value-previous['v(h_drivecol)']))
        previous=row
    periods=[b-a for a,b in zip(edges,edges[1:])]
    complete=previous is not None and abs(previous['time']-.005)<1e-12
    return dict(complete=complete,edges=len(edges),period_s=statistics.median(periods) if periods else None,
                period_spread_s=max(periods)-min(periods) if periods else None,
                collector_min_v=low,collector_max_v=high,forced_control_current_a=current_j/span if span else None)


def recorded_cycles(path,period_s=62.5e-6,samples=256):
    """Extract last complete cycles, explicitly retimed for open-loop isolation."""
    window=deque()
    for row in steady_supply.raw_rows(path):
        window.append(row)
        while len(window)>2 and window[1]['time']<row['time']-8*period_s:window.popleft()
    rows=list(window)
    if len(rows)<2:raise ValueError('missing recorded isolation window')
    times=[r['time'] for r in rows];waves={};periods={}
    for name,trigger,threshold in (('sync','v(sync_c)',5.),('feedback','v(h_hot)',150.)):
        crossings=[]
        for a,b in zip(rows,rows[1:]):
            if a[trigger]<threshold<=b[trigger]:
                crossings.append(a['time']+(b['time']-a['time'])*(threshold-a[trigger])/(b[trigger]-a[trigger]))
        if len(crossings)<2:raise ValueError('missing isolated cycle '+name)
        start,end=crossings[-2:];values=[]
        channel='v(sync_c)' if name=='sync' else 'v(h_feedback)'
        for i in range(samples):
            t=start+(end-start)*i/samples;j=bisect.bisect_right(times,t)
            a,b=rows[j-1],rows[j];f=(t-a['time'])/(b['time']-a['time'])
            values.append(a[channel]+f*(b[channel]-a[channel]))
        waves[name]=values;periods[name]=end-start
    with Path(path).open('rb') as stream:trace_hash=digest_stream(stream)
    return dict(waveforms=waves,original_periods_s=periods,isolation_period_s=period_s,
                trace_sha256=trace_hash,
                qualification='retimed-recorded-cycle-isolation',connected_lock_verified=False)


def phase_sweep(output,runtime,trace,parameters=None,seconds=120):
    out=Path(output);out.mkdir(parents=True,exist_ok=False)
    (out/'runner.py').write_bytes(Path(__file__).read_bytes())
    wave=recorded_cycles(trace);(out/'stimulus.json').write_text(json.dumps(wave,indent=2)+'\n')
    report=dict(format='dac-horizontal-phase-isolation-v1',connected_lock_verified=False,
        qualification=wave['qualification'],trials=[],stimulus_sha256=lab.digest((out/'stimulus.json').read_bytes()))
    deadline=time.monotonic()+seconds
    for phase in range(16):
        if time.monotonic()>=deadline:break
        deck,meta=make_deck(parameters or {},0)
        deck=deck.replace('Vcontrol h_control 0 0\n','')
        for name,node in (('sync','sync_c'),('feedback','h_feedback')):
            values=wave['waveforms'][name];n=len(values);shift=phase*n//16 if name=='feedback' else 0
            pairs=[f'{i*wave["isolation_period_s"]/n:.15g} {values[(i-shift)%n]:.15g}' for i in range(n+1)]
            deck=deck.replace(f'V{name} {node} 0 0',f'V{name} {node} 0 PWL('+ ' '.join(pairs)+') r=0')
        deck=deck.replace('.save time v(h_drivecol) v(h_control) i(Vcontrol)',
                          '.save time v(h_control) @d1032[id] @d1033[id]')
        trial=out/str(phase);result=steady_supply.solve(deck,trial,runtime,timeout_s=deadline-time.monotonic())
        meta.update(qualification=wave['qualification'],phase_lines=phase/16)
        meta.pop('control_voltage_v')
        (trial/'metadata.json').write_text(json.dumps(meta,indent=2)+'\n')
        entry=dict(phase_lines=phase/16,solve=result)
        if result['status']=='complete':
            previous=None;integral=0.;span=0.;low=None;high=None
            for row in steady_supply.raw_rows(trial/'trace.raw'):
                value=row['v(h_control)'];low=value if low is None else min(low,value);high=value if high is None else max(high,value)
                if previous:
                    dt=row['time']-previous['time'];span+=dt
                    integral+=dt*(value+previous['v(h_control)'])/2
                previous=row
            entry['measurement']=dict(complete=previous is not None and abs(previous['time']-.005)<1e-12,
                mean_control_v=integral/span if span else None,min_control_v=low,max_control_v=high)
        report['trials'].append(entry)
        (out/'phase-isolation.json').write_text(json.dumps(report,indent=2)+'\n')
    report['status']='complete' if len(report['trials'])==16 and all(t.get('measurement',{}).get('complete') for t in report['trials']) else 'blocked'
    (out/'phase-isolation.json').write_text(json.dumps(report,indent=2)+'\n')
    return report


def run(output,runtime,parameters=None,seconds=120):
    out=Path(output);out.mkdir(parents=True,exist_ok=False)
    (out/'runner.py').write_bytes(Path(__file__).read_bytes())
    deadline=time.monotonic()+seconds
    report=dict(format='dac-horizontal-tuning-isolation-v1',qualification='forced-control-isolation',
                full_monitor_qualified=False,connected_lock_verified=False,trials=[])
    for i,voltage in enumerate((-4.,0.,4.,8.,12.,18.)):
        if time.monotonic()>=deadline:break
        deck,meta=make_deck(parameters or {},voltage)
        trial=out/str(i);result=steady_supply.solve(deck,trial,runtime,timeout_s=deadline-time.monotonic())
        (trial/'metadata.json').write_text(json.dumps(meta,indent=2)+'\n')
        entry=dict(metadata=meta,solve=result)
        if result['status']=='complete':entry['measurement']=summarize(trial/'trace.raw')
        report['trials'].append(entry)
        (out/'isolation.json').write_text(json.dumps(report,indent=2)+'\n')
    measured=[t for t in report['trials'] if t.get('measurement',{}).get('complete') and t['measurement']['period_s']]
    report['tuning_intervals']=[dict(control_v=[a['metadata']['control_voltage_v'],b['metadata']['control_voltage_v']],
        frequency_hz=[1/a['measurement']['period_s'],1/b['measurement']['period_s']],
        frequency_slope_hz_per_v=(1/b['measurement']['period_s']-1/a['measurement']['period_s'])/(b['metadata']['control_voltage_v']-a['metadata']['control_voltage_v']))
        for a,b in zip(measured,measured[1:])]
    report['status']='complete' if len(measured)==6 else 'blocked'
    (out/'isolation.json').write_text(json.dumps(report,indent=2)+'\n')
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--runtime',type=Path,required=True)
    parser.add_argument('--phase-trace',type=Path,help='Recorded connected trace; retime its last complete cycles for an explicitly open-loop phase sweep')
    parser.add_argument('--tank-h',type=float,default=.001532)
    args=parser.parse_args()
    result=(phase_sweep(args.output,args.runtime,args.phase_trace,{'horizontal_tank_l':args.tank_h}) if args.phase_trace else
            run(args.output,args.runtime,{'horizontal_tank_l':args.tank_h}))
    print(json.dumps(result,indent=2))
    raise SystemExit(0 if result['status']=='complete' else 2)
