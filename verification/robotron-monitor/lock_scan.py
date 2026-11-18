#!/usr/bin/env python3
"""Bounded trim scan of the connected monitor; no prescribed scan stimulus.

Adjacent passing samples bracket a *sampled* lock interval, not a proof of
continuous stability. Its midpoint must pass a fresh connected solve.
"""
import argparse
import json
from pathlib import Path
import time
import lab
import steady_supply
import transformer_candidates


def midpoint(trials):
    groups=[];current=[]
    for trial in sorted(trials,key=lambda t:t['trim']):
        if trial['accepted']:current.append(trial['trim'])
        else:
            if current:groups.append(current)
            current=[]
    if current:groups.append(current)
    groups=[g for g in groups if len(g)>=2]
    if not groups:return None
    selected=max(groups,key=lambda g:(g[-1]-g[0],-g[0]))
    return dict(lower=selected[0],upper=selected[-1],midpoint=(selected[0]+selected[-1])/2,
                qualification='adjacent-sampled-lock-bracket')


def refine_bracket(trials, trial, deadline, *, iterations=5):
    """Bisect each observed pass/fail boundary, never infer an untested pass."""
    bracket=midpoint(trials)
    if bracket is None:return None
    for side in ('lower','upper'):
        passed=bracket[side]
        failed=[t['trim'] for t in trials if not t['accepted'] and
                (t['trim']<passed if side=='lower' else t['trim']>passed)]
        if not failed:continue
        outside=max(failed) if side=='lower' else min(failed)
        for i in range(iterations):
            if time.monotonic()>=deadline:break
            value=(outside+passed)/2
            result=trial(value,f'boundary-{side}-{i}')
            trials.append(result)
            if result['accepted']:passed=value
            else:outside=value
        bracket[side]=passed
        bracket[side+'_outside']=outside
    bracket['midpoint']=(bracket['lower']+bracket['upper'])/2
    bracket['qualification']='refined-sampled-lock-bracket'
    return bracket


def run(capture,output,runtime,candidate,*,hours=12,settings=None):
    if not 0<hours<=12:raise ValueError('wall budget must be in (0,12] hours')
    settings=settings or {};unknown=set(settings)-{'parameters','solver','magnetic_parameters','yoke_profile'}
    if unknown:raise ValueError('unknown lock scan settings')
    out=Path(output).resolve();out.mkdir(parents=True,exist_ok=False)
    begin=time.monotonic();deadline=begin+hours*3600
    search_deadline=begin+hours*2400
    data=Path(capture).read_bytes();(out/'input.json').write_bytes(data)
    capture_data=lab.parse_capture(out/'input.json')
    if capture_data['qualification']!='schematic-derived-logical':raise ValueError('native firmware capture required')
    selection=steady_supply.select(capture_data)
    if selection['status']!='complete':raise ValueError(selection['reason'])
    assembly=steady_supply.assemble(out/'assembly',yoke_path=settings.get('yoke_profile'))
    steady_supply.tune(assembly,selection,settings.get('parameters'))
    if 'magnetic_parameters' in settings:
        raw=Path(settings['magnetic_parameters']).read_bytes()
        (out/'assembly/magnetic-override.json').write_bytes(raw)
        assembly['magnetic_parameters']=json.loads(raw)
    candidates=[c for c in transformer_candidates.enumerate_candidates(assembly['magnetic_graph']) if c['id']==candidate]
    if len(candidates)!=1:raise ValueError('explicit known candidate required')
    report=dict(format='dac-connected-lock-scan-v1',status='incomplete',trials=[],candidate=candidate,
        settings=settings,capture_sha256=lab.digest(data),selected_trim=None,full_monitor_qualified=False,validation_reserved_s=hours*1200)
    def save():(out/'scan.json').write_text(json.dumps(report,indent=2)+'\n')
    def trial(trim,name,*,initial=None,limit=None):
        steady_supply.tune(assembly,selection,{'horizontal_trim_fraction':trim})
        options=dict(settings.get('solver',{}))
        if initial is not None:options['initial_voltages']=initial
        deck,meta=steady_supply.deck(assembly,selection,candidates[0],fields=8,**options)
        path=out/name
        solved=steady_supply.solve(deck,path,runtime,timeout_s=max(.001,(limit or search_deadline)-time.monotonic()))
        (path/'metadata.json').write_text(json.dumps(meta,indent=2)+'\n')
        entry=dict(trim=trim,solve=solved,accepted=False,parameters=meta['parameters'],initial_voltages=options.get('initial_voltages',{}))
        if solved['status']=='complete':
            entry['settling']=steady_supply.assess(path/'trace.raw',meta,selection)
            entry['accepted']=entry['settling']['accepted']
        return entry
    save()
    try:
        # Low-to-high order is deterministic; an interrupted scan never bridges
        # an untested point or promotes a single passing setting to an interval.
        for i in range(9):
            if time.monotonic()>=search_deadline:break
            report['trials'].append(trial(.01+.98*i/8,f'trim-{i}'));save()
            if midpoint(report['trials']) is not None:break
        bracket=refine_bracket(report['trials'],trial,search_deadline);report['sampled_interval']=bracket;save()
        if bracket and time.monotonic()<deadline:
            report['midpoint_validation']=trial(bracket['midpoint'],'midpoint',limit=deadline)
            if report['midpoint_validation']['accepted'] and time.monotonic()<deadline:
                initial={k:(lo+hi)/2 for k,(lo,hi) in steady_supply.INITIAL_VOLTAGE_BOUNDS.items()}
                if initial==settings.get('solver',{}).get('initial_voltages',{}):initial={}
                report['independent_initialization']=trial(bracket['midpoint'],'midpoint-independent',initial=initial,limit=deadline)
                if report['independent_initialization']['accepted']:
                    import steady_acceptance
                    meta=json.loads((out/'midpoint/metadata.json').read_text())
                    report['initialization_comparison']=steady_acceptance.compare(out/'midpoint/trace.raw',out/'midpoint-independent/trace.raw',meta)
                    if report['initialization_comparison']['accepted']:report['selected_trim']=bracket['midpoint']
        report['status']='lock-candidate' if report['selected_trim'] is not None else 'blocked'
        report['reason']='A lock candidate passed two initializations; numerical/physical acceptance remains required.' if report['selected_trim'] is not None else 'No validated adjacent-sample lock interval within the tested settings and wall budget.'
        save();return report
    except Exception as error:
        report.update(status='failed',reason=str(error));save();raise


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('capture','output','runtime'):p.add_argument('--'+n,type=Path,required=True)
    p.add_argument('--candidate',required=True);p.add_argument('--wall-budget-hours',type=float,default=12)
    p.add_argument('--settings',type=Path,help='Explicit parameters, solver options, and optional magnetic_parameters file')
    a=p.parse_args();result=run(a.capture,a.output,a.runtime,a.candidate,hours=a.wall_budget_hours,
        settings=json.loads(a.settings.read_text()) if a.settings else None)
    print(json.dumps(result,indent=2));raise SystemExit(0 if result['status']=='lock-candidate' else 2)
