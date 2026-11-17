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


def run(capture,output,runtime,candidate,*,hours=12,settings=None):
    if not 0<hours<=12:raise ValueError('wall budget must be in (0,12] hours')
    settings=settings or {};unknown=set(settings)-{'parameters','solver','magnetic_parameters'}
    if unknown:raise ValueError('unknown lock scan settings')
    out=Path(output).resolve();out.mkdir(parents=True,exist_ok=False)
    deadline=time.monotonic()+hours*3600
    data=Path(capture).read_bytes();(out/'input.json').write_bytes(data)
    selection=steady_supply.select(lab.parse_capture(out/'input.json'))
    if selection['status']!='complete':raise ValueError(selection['reason'])
    assembly=steady_supply.assemble(out/'assembly')
    steady_supply.tune(assembly,selection,settings.get('parameters'))
    if 'magnetic_parameters' in settings:
        raw=Path(settings['magnetic_parameters']).read_bytes()
        (out/'assembly/magnetic-override.json').write_bytes(raw)
        assembly['magnetic_parameters']=json.loads(raw)
    candidates=[c for c in transformer_candidates.enumerate_candidates(assembly['magnetic_graph']) if c['id']==candidate]
    if len(candidates)!=1:raise ValueError('explicit known candidate required')
    report=dict(format='dac-connected-lock-scan-v1',status='incomplete',trials=[],candidate=candidate,
        settings=settings,capture_sha256=lab.digest(data),selected_trim=None,full_monitor_qualified=False)
    def save():(out/'scan.json').write_text(json.dumps(report,indent=2)+'\n')
    def trial(trim,name):
        steady_supply.tune(assembly,selection,{'horizontal_trim_fraction':trim})
        deck,meta=steady_supply.deck(assembly,selection,candidates[0],fields=8,**settings.get('solver',{}))
        path=out/name
        solved=steady_supply.solve(deck,path,runtime,timeout_s=max(.001,deadline-time.monotonic()))
        (path/'metadata.json').write_text(json.dumps(meta,indent=2)+'\n')
        entry=dict(trim=trim,solve=solved,accepted=False)
        if solved['status']=='complete':
            entry['settling']=steady_supply.assess(path/'trace.raw',meta,selection)
            entry['accepted']=entry['settling']['accepted']
        return entry
    save()
    try:
        # Low-to-high order is deterministic; an interrupted scan never bridges
        # an untested point or promotes a single passing setting to an interval.
        for i in range(9):
            if time.monotonic()>=deadline:break
            report['trials'].append(trial(.01+.98*i/8,f'trim-{i}'));save()
        bracket=midpoint(report['trials']);report['sampled_interval']=bracket
        if bracket and time.monotonic()<deadline:
            report['midpoint_validation']=trial(bracket['midpoint'],'midpoint')
            if report['midpoint_validation']['accepted']:report['selected_trim']=bracket['midpoint']
        report['status']='lock-candidate' if report['selected_trim'] is not None else 'blocked'
        report['reason']='A lock candidate still requires independent initialization and numerical/physical acceptance.' if report['selected_trim'] is not None else 'No validated adjacent-sample lock interval within the tested settings and wall budget.'
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
