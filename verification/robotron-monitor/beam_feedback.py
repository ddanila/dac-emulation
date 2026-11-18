"""Bounded periodic electrode-load iteration; electrical lock remains separate."""
import copy,json,math,subprocess,sys,time
from pathlib import Path
import collection,electrical_cache,steady_supply,steady_trace,steady_acceptance


def residual(a,b):
    collection.validate(a);collection.validate(b)
    if a['period_s']!=b['period_s'] or a['bins']!=b['bins']:raise ValueError('collection grids differ')
    return max(math.sqrt(math.fsum((x-y)**2 for x,y in zip(a['currents_a'][k],b['currents_a'][k]))/
                         max(math.fsum(y*y for y in b['currents_a'][k]),1e-30)) for k in a['currents_a'])


def relax(old,new,alpha):
    if not math.isfinite(alpha) or not 0<alpha<=1:raise ValueError('invalid load relaxation')
    residual(old,new);r=copy.deepcopy(new)
    r['currents_a']={k:[x+alpha*(y-x) for x,y in zip(old['currents_a'][k],new['currents_a'][k])] for k in new['currents_a']}
    r['collected_charge_c']={k:math.fsum(v)*r['period_s']/r['bins'] for k,v in r['currents_a'].items()}
    r['emitted_charge_c']=math.fsum(r['collected_charge_c'].values());r['integrated_launch_charge_c']=r['emitted_charge_c']
    r['charge_relative_error']=0.;r['unresolved_fraction']=r['collected_charge_c']['unresolved']/max(r['emitted_charge_c'],1e-30)
    r['qualification']='relaxed-predictor-load-not-a-converged-collection-measurement'
    for key in ('terminal_kinetic_j','launch_energy_j','trajectory_electric_work_j','surface_charge_c','late_arrival_charge_c'):
        r.pop(key,None)
    collection.validate(r);return r


def collect(trace,output,field,deadline,*,fine=False,bins=None):
    path=Path(output);field_path=path.with_suffix('.field.json');field_path.write_text(json.dumps(field)+'\n')
    remaining=deadline-time.monotonic()
    if remaining<=0:raise TimeoutError('collection wall budget exhausted')
    cmd=[sys.executable,str(Path(collection.__file__)), '--trace',str(trace),'--output',str(path),'--field-parameters',str(field_path)]
    if fine:cmd+=['--trajectory-step-m','.0001','--max-interval-s',str(1/55296000)]
    if bins is not None:cmd+=['--bins',str(bins)]
    with path.with_suffix('.log').open('w') as log:
        subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=remaining)
    result=json.loads(path.read_text());collection.validate(result);return result


def run(assembly,selection,candidate,metadata,base_trial,output,runtime,solver,deadline,*,cache=None,max_iterations=20,fine=False):
    if type(max_iterations) is not int or not 2<=max_iterations<=20:raise ValueError('expected 2..20 coupling iterations')
    out=Path(output).resolve();out.mkdir(parents=True,exist_ok=False)
    report=dict(format='dac-electrode-feedback-v1',status='blocked',iterations=[],converged=False,
                accepted=False,full_monitor_qualified=False,profile=collection.PROFILE)
    def save():(out/'feedback.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    save();a=dict(assembly);old=None;previous_trial=Path(base_trial);alpha=.5;previous_error=None;passes=0
    try:
        if deadline<=time.monotonic():raise TimeoutError('feedback wall budget exhausted')
        report['initial_settling']=steady_supply.assess(previous_trial/'trace.raw',metadata,selection);save()
        if not report['initial_settling']['accepted']:raise ValueError('feedback requires a synchronized periodic input state')
        end=metadata['period_s']*metadata['simulated_fields'];trace=out/'initial.csv'
        exported=steady_trace.export(previous_trial/'trace.raw',trace,start_s=end-metadata['period_s'],end_s=end)
        if exported['current_definition']!='post-grid2-launch':raise ValueError('coupling requires an explicit launch-current trace')
        bins=math.ceil(metadata['period_s']*27648000-1e-9)*(2 if fine else 1)
        old=collect(trace,out/'initial-collection.json',metadata['yoke']['field'],deadline,fine=fine,bins=bins)
        for i in range(max_iterations):
            if deadline<=time.monotonic():raise TimeoutError('feedback wall budget exhausted')
            a['collection_report']=old
            text,meta=steady_supply.deck(a,selection,candidate,fields=metadata['simulated_fields'],**solver)
            folder=out/f'iteration-{i:02d}'
            solved=electrical_cache.solve(text,folder,runtime,timeout_s=deadline-time.monotonic(),cache=cache)
            (folder/'metadata.json').write_text(json.dumps(meta,indent=2)+'\n')
            entry=dict(solve=solved,trial=str(folder),relaxation=alpha);report['iterations'].append(entry);save()
            if solved['status']!='complete':raise ValueError('coupled electrical solve failed')
            entry['settling']=steady_supply.assess(folder/'trace.raw',meta,selection)
            report['latest_completed']=dict(solve=solved,trial=str(folder),metadata=meta,settling=entry['settling']);save()
            end=meta['period_s']*meta['simulated_fields'];trace=folder/'field.csv'
            steady_trace.export(folder/'trace.raw',trace,start_s=end-meta['period_s'],end_s=end)
            new=collect(trace,folder/'collection.json',meta['yoke']['field'],deadline,fine=fine,bins=bins)
            err=residual(old,new)
            entry['load_relative_error']=err
            entry['waveform_comparison']=steady_acceptance.compare(previous_trial/'trace.raw',folder/'trace.raw',meta)
            charge_error=abs(old['collected_charge_c']['anode']-new['emitted_charge_c'])/max(new['emitted_charge_c'],1e-30)
            entry['periodic_charge_relative_error']=charge_error
            # Sub-percent load convergence alone is insufficient for the tighter
            # charge ledger: mean emission and collection must also agree.
            passed=err<.01 and charge_error<.001 and entry['waveform_comparison']['accepted']
            passes=passes+1 if passed else 0
            entry['consecutive_passes']=passes;save()
            if passes>=2:
                report.update(converged=True,status='complete',accepted=entry['settling']['accepted'],
                    trial=str(folder),metadata=meta,settling=entry['settling'],collection=str(folder/'collection.json'),
                    load=old,charge_relative_error=charge_error)
                break
            if previous_error is not None and err>previous_error:
                alpha/=2
                if alpha<1/64:raise ValueError('coupling residual worsens at minimum relaxation')
            old=relax(old,new,alpha);previous_error=err;previous_trial=folder
        else:report['reason']='coupling iteration budget exhausted'
    except (ValueError,TimeoutError,subprocess.TimeoutExpired,subprocess.CalledProcessError) as error:
        report['reason']=str(error)
    save();return report
