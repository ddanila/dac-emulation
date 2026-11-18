"""Independent instrumented solve and beam/circuit accounting gates."""
import json,time,subprocess
from pathlib import Path
import energy_ledger,electrical_cache,steady_supply,steady_acceptance,steady_trace,beam_feedback


def run(assembly,selection,candidate,metadata,trial,output,runtime,solver,deadline,*,cache=None,fine=False):
    try:
        return _run(assembly,selection,candidate,metadata,trial,output,runtime,solver,deadline,cache=cache,fine=fine)
    except (TimeoutError,subprocess.TimeoutExpired,ValueError,subprocess.CalledProcessError) as error:
        path=Path(output)/'validation.json'
        report=json.loads(path.read_text())
        report.update(status='blocked' if isinstance(error,(TimeoutError,subprocess.TimeoutExpired)) else 'failed',accepted=False,reason=str(error))
        path.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
        return report


def _run(assembly,selection,candidate,metadata,trial,output,runtime,solver,deadline,*,cache=None,fine=False):
    out=Path(output).resolve();out.mkdir(parents=True,exist_ok=False)
    report=dict(format='dac-electrical-energy-validation-v1',accepted=False,status='blocked')
    def save():(out/'validation.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    save()
    if time.monotonic()>=deadline:report['reason']='energy validation budget exhausted';save();return report
    text,meta=steady_supply.deck(assembly,selection,candidate,fields=metadata['simulated_fields'],**solver)
    text,inventory=energy_ledger.instrument(text,out/'inventory',runtime)
    remaining=deadline-time.monotonic()
    if remaining<=0:report['reason']='energy validation budget exhausted';save();return report
    folder=out/'electrical';solved=electrical_cache.solve(text,folder,runtime,timeout_s=remaining,cache=cache)
    report['solve']=solved;save()
    if solved['status']!='complete':report['reason']='instrumented solve failed';save();return report
    (folder/'metadata.json').write_text(json.dumps(meta,indent=2)+'\n')
    report['comparison']=steady_acceptance.compare(Path(trial)/'trace.raw',folder/'trace.raw',meta)
    report['settling']=steady_supply.assess(folder/'trace.raw',meta,selection)
    end=meta['period_s']*meta['simulated_fields'];start=end-meta['period_s']
    report['circuit']=energy_ledger.assess(folder/'trace.raw',inventory,start_s=start,end_s=end,
        core=meta['candidate']['numerical_parameters']['core'],deadline=deadline)
    trace=out/'field.csv';report['trace']=steady_trace.export(folder/'trace.raw',trace,start_s=start,end_s=end)
    if report['trace']['raw_sha256']!=report['circuit']['raw_sha256']:raise ValueError('energy and collection trace identities differ')
    c=beam_feedback.collect(trace,out/'collection.json',meta['yoke']['field'],deadline,fine=fine,bins=assembly['collection_report']['bins'])
    # Keep beam error normalized to beam work, independently of rail power.
    measured=report['circuit']['groups_j']['beam_work'];predicted=c['trajectory_electric_work_j']
    error=abs(measured-predicted)/max(abs(measured),abs(predicted),1e-30)
    report['beam']=dict(electrical_work_j=measured,trajectory_work_j=predicted,
        launch_energy_j=c['launch_energy_j'],terminal_kinetic_j=c['terminal_kinetic_j'],
        relative_error=error,accepted=error<.01 and c['charge_accepted'])
    report['accepted']=all(report[k]['accepted'] for k in ('comparison','settling','circuit','beam'))
    report['status']='complete';report['trial']=str(folder);report['metadata']=meta
    save();return report
