"""Independent electrical replay checks and bounded single-frame orchestration."""
import array
import json
import math
from pathlib import Path
import subprocess
import sys
import time
import steady_supply
import steady_trace

NAMES=('v(eht)','v(g2)','v(g4)','v(cathode)','i(lhorizontal)',
       'i(lvertical)','v(x1136.xshared.flux_b)','i(@b.xcrt.bbeam[i])')
FLOORS=(1.,.01,.01,.001,1e-6,1e-6,1e-6,1e-9)


def sample(path, start, end, count):
    values=[array.array('d') for _ in NAMES];previous=None;j=0
    last=None
    for row in steady_supply.raw_rows(path):
        last=row['time']
        if previous is not None:
            while j<count:
                t=start+(j+.5)*(end-start)/count
                if t>row['time']:break
                if t<previous['time']:raise ValueError('missing comparison window')
                f=(t-previous['time'])/(row['time']-previous['time'])
                for name,v in zip(NAMES,values):v.append(previous[name]+f*(row[name]-previous[name]))
                j+=1
        previous=row
    if j!=count or last<end-1e-12:raise ValueError('incomplete comparison window')
    return values


def compare(base, other, metadata, *, sample_hz=27648000):
    period=metadata['period_s'];end=period*metadata['simulated_fields'];count=math.ceil(period*sample_hz)
    if not 1<=count<=2000000:raise ValueError('invalid electrical comparison bandwidth')
    a=sample(base,end-period,end,count);b=sample(other,end-period,end,count)
    errors={}
    for name,x,y,floor in zip(NAMES,a,b,FLOORS):
        scale=max(floor,math.sqrt(sum(v*v for v in x)/count),math.sqrt(sum(v*v for v in y)/count))
        errors[name]=math.sqrt(sum((u-v)**2 for u,v in zip(x,y))/count)/scale
    return dict(accepted=all(v<.01 for v in errors.values()),relative_rms_error=errors,
        sample_hz=sample_hz,samples=count,threshold=.01,
        full_monitor_qualified=False,scope='same-phase-electrical-waveforms')


def optical_worker(trace, output, deadline, *, spatial=False, fine=False, field_path=None, diagnostic=False):
    remaining=deadline-time.monotonic()
    if remaining<=0:return dict(status='blocked',reason='whole-run wall budget exhausted')
    root=Path(__file__).parent
    cmd=[sys.executable,str(root/'periodic_frame.py'),'--trace',str(trace),'--output',str(output),'--assume-periodic']
    cmd+=['--cache',str(output.parent.parent.parent/'optical-cache')]
    if field_path is not None:cmd+=['--field-parameters',str(field_path)]
    if diagnostic:cmd+=['--width','240','--height','180','--max-interval-s',str(200e-9)]
    if spatial:cmd+=['--width','960','--height','720']
    if fine:cmd+=['--trajectory-step-m','.0001','--max-interval-s',str(1/55296000)]
    try:
        with output.with_suffix('.log').open('w') as log:
            result=subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,timeout=remaining,check=False)
    except subprocess.TimeoutExpired:return dict(status='blocked',reason='whole-run wall budget exhausted during optical integration')
    if result.returncode:return dict(status='failed',reason='optical worker failed; see log')
    return dict(status='complete',manifest=str(output/'frame.json'))


def diagnose(trial, metadata, capture, field, deadline):
    trial=Path(trial)
    if time.monotonic()>=deadline:return dict(status='blocked',reason='diagnostic wall budget exhausted')
    end=metadata['period_s']*metadata['simulated_fields'];trace=trial/'diagnostic-field.csv'
    report=steady_trace.export(trial/'trace.raw',trace,start_s=end-metadata['period_s'],end_s=end)
    field_path=trial/'field-parameters.json';field_path.write_text(json.dumps(field,indent=2)+'\n')
    cmd=[sys.executable,str(Path(__file__).parent/'scan_diagnostics.py'),'--trace',str(trace),
         '--capture',str(capture),'--output',str(trial/'diagnostics'),'--field-parameters',str(field_path)]
    try:
        with (trial/'diagnostics.log').open('w') as log:
            result=subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,timeout=max(.001,deadline-time.monotonic()))
    except subprocess.TimeoutExpired:return dict(status='blocked',trace=report,reason='diagnostic wall budget exhausted')
    return dict(status='complete' if result.returncode==0 else 'failed',trace=report,
                report=str(trial/'diagnostics/diagnostics.json'),log=str(trial/'diagnostics.log'))


def diagnostic_frame(trial,metadata,output,settling,deadline):
    """Render this completed trial only, preserving its failed electrical checks."""
    out=Path(output);out.mkdir(parents=True,exist_ok=False)
    report=dict(format='dac-connected-diagnostic-frame-v1',status='blocked',
        qualification='unaccepted-connected-trial',accepted_warmed_frame=False,
        full_monitor_qualified=False,specimen_validated=False,
        source_trial=str(Path(trial).resolve()),settling=settling,experiment=metadata.get('experiment'),outputs={})
    def save():
        (out/'diagnostic.json').write_text(json.dumps(report,indent=2)+'\n')
        return report
    save()
    if time.monotonic()>=deadline:
        report['reason']='render budget exhausted; no older image substituted';return save()
    import hashlib
    deck=Path(trial)/'run.cir'
    report['deck_sha256']=hashlib.sha256(deck.read_bytes()).hexdigest()
    report['run_id']=report['deck_sha256'][:16]
    end=metadata['period_s']*metadata['simulated_fields']
    trace=out/'field.csv'
    report['trace']=steady_trace.export(Path(trial)/'trace.raw',trace,start_s=end-metadata['period_s'],end_s=end)
    field=metadata.get('yoke',{}).get('field',{})
    path=out/'field-parameters.json';path.write_text(json.dumps(field,indent=2)+'\n')
    report['preview_settings']=dict(width=240,height=180,max_interval_s=200e-9,trajectory_step_m=.0002,refinement_verified=False)
    report['render']=optical_worker(trace,out/'optical',deadline,field_path=path,diagnostic=True)
    if report['render']['status']=='complete':
        report['status']='diagnostic-only'
        report['outputs']={name:str(Path('optical')/name) for name in ('frame.png','frame.f32','frame.json')}
    else:report['reason']=report['render'].get('reason','render did not complete')
    return save()


def finish(assembly, selection, candidate, metadata, trial, output, runtime, solver, deadline, *, electrical_cache=None):
    """Only called after settling; every independent failure stops promotion."""
    out=Path(output);out.mkdir(parents=True,exist_ok=False)
    report=dict(format='dac-steady-reference-acceptance-v1',status='blocked',checks={},blockers=[],
        accepted_warmed_frame=False,full_monitor_qualified=False,specimen_validated=False)
    def save():
        (out/'acceptance.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
        return report
    save()
    variants={
        'refinement':dict(solver,max_step_s=metadata['max_step_s']/2,
                          reltol=max(1e-5,metadata['reltol']/5),abstol=max(1e-12,metadata['abstol']/10)),
        'initialization':dict(solver,initial_voltages={n:(lo+hi)/2 for n,(lo,hi) in steady_supply.INITIAL_VOLTAGE_BOUNDS.items()})}
    if variants['initialization']['initial_voltages']==metadata.get('initial_voltage_guesses'):
        variants['initialization']['initial_voltages']={}
    for name,options in variants.items():
        remaining=deadline-time.monotonic()
        if remaining<=0:report['blockers'].append('whole-run wall budget exhausted');return save()
        deck,meta=steady_supply.deck(assembly,selection,candidate,fields=metadata['simulated_fields'],**options)
        destination=out/name
        import electrical_cache as trace_cache
        solved=trace_cache.solve(deck,destination,runtime,timeout_s=remaining,cache=electrical_cache)
        (destination/'metadata.json').write_text(json.dumps(meta,indent=2)+'\n')
        check=dict(solve=solved,trial=str(destination.resolve()),metadata=meta);report['checks'][name]=check;save()
        if solved['status']!='complete':report['blockers'].append(name+' solver failed');return save()
        check['settling']=steady_supply.assess(destination/'trace.raw',meta,selection)
        check['comparison']=compare(Path(trial)/'trace.raw',destination/'trace.raw',metadata)
        if not check['settling']['accepted'] or not check['comparison']['accepted']:
            report['blockers'].append(name+' failed settling or waveform agreement');return save()
        save()
    trace=out/'field.csv';end=metadata['period_s']*metadata['simulated_fields']
    report['trace']=steady_trace.export(Path(trial)/'trace.raw',trace,start_s=end-metadata['period_s'],end_s=end);save()
    field_path=out/'field-parameters.json'
    field_path.write_text(json.dumps(assembly['yoke']['field'],indent=2)+'\n')
    for name,options in (('optical',{}),('optical-fine',dict(fine=True)),('optical-spatial',dict(spatial=True))):
        report['checks'][name]=optical_worker(trace,out/name,deadline,field_path=field_path,**options);save()
        if report['checks'][name]['status']!='complete':report['blockers'].append(name+' did not complete');return save()
    import periodic_frame
    report['checks']['optical-integration']=periodic_frame.compare(out/'optical',out/'optical-fine')
    report['checks']['optical-spatial-refinement']=periodic_frame.compare(out/'optical',out/'optical-spatial',spatial=True)
    for name in ('optical-integration','optical-spatial-refinement'):
        if not report['checks'][name]['accepted']:report['blockers'].append(name+' failed')
    # A stable numerical image is necessary but insufficient. Keep these physical
    # gates explicit until electrode interception and the circuit energy ledger
    # exist; never silently equate optical energy closure with electrical closure.
    report['blockers'] += ['Trajectory interception is not coupled back to electrode loads.',
                          'Complete circuit power/storage/loss energy closure is not implemented.']
    if not assembly['yoke']['inductance_field_relationship_verified']:
        report['blockers'].append('Yoke inductance and magnetic deflection remain independently assumed.')
    return save()
