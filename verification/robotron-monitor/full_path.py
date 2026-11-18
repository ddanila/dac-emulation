#!/usr/bin/env python3
"""Prepare a firmware-to-CRT run and enforce the assembly publication gate.

The default mode stops at preflight. The experimental steady-supply mode
runs connected electrical candidate screens; it does not yet qualify a frame. It intentionally cannot promote an arbitrary electrical trace, stage
bench or plausible-looking optical replay into a full-circuit firmware image.
"""
import argparse,json,subprocess
from pathlib import Path
import frames,full_path_audit,lab,transformer_candidates,sustained as sustained_gate
ROOT=Path(__file__).resolve().parent


def run(capture,output,*,profile='k7222-11',candidate=None,fields=1,pre_roll_fields=1,sustained=False):
    if profile!='k7222-11':raise ValueError('unsupported full-path monitor profile')
    graph=ROOT/'reference/k7222-11/t3-winding-hypothesis.json'
    candidates=transformer_candidates.enumerate_candidates(json.loads(graph.read_text()))
    ids=[c['id'] for c in candidates]
    if candidate is not None and candidate not in ids:raise ValueError('unknown transformer candidate')
    out=Path(output).resolve();out.mkdir(parents=True,exist_ok=False)
    report=dict(format='dac-monitor-full-path-run-v1',status='incomplete',profile=profile,
        qualification='preflight-only',full_monitor_qualified=False,
        assembly_complete=False,numerical_acceptance=False,specimen_validated=False,
        transformer_candidate=candidate,available_candidates=ids,
        outputs={},blockers=[],hashes={},thermal_equilibrium=False,
        electrical_stability=False,optical_stability=False,
        target=dict(initialization='thermal-equilibrium',fields=16 if sustained else fields,
                    stable_fields_before_output=8 if sustained else None,
                    phosphor_preroll_decay_constants=7 if sustained else None))
    def save():(out/'run.json').write_text(json.dumps(report,indent=2)+'\n')
    save()
    try:
        selected=frames.prepare(capture,out/'capture',fields=fields,pre_roll_fields=pre_roll_fields)
        if sustained:
            selection=sustained_gate.select(lab.parse_capture(out/'capture/input.json'))
            selected.update(selection)
            (out/'capture/fields.json').write_text(json.dumps(selected,indent=2)+'\n')
        audit=full_path_audit.audit(out/'assembly')
        report['outputs']={'field_selection':'capture/fields.json','assembly_audit':'assembly/audit.json'}
        report['hashes']={'capture':selected['capture_sha256'],
            'audit':lab.digest((out/'assembly/audit.json').read_bytes()),
            'winding_hypothesis':lab.digest(graph.read_bytes())}
        for name in ('full_path.py','frames.py','full_path_audit.py','sustained.py'):
            raw=(ROOT/name).read_bytes();(out/name).write_bytes(raw);report['hashes'][name]=lab.digest(raw)
        report['selection']=selected['selection']
        report['blockers']=audit['blockers'].copy()
        if selected['status']!='complete':report['blockers'].append(dict(id='capture-fields',required=selected['reason']))
        if selected['qualification']!='schematic-derived-logical':report['blockers'].append(dict(id='firmware-provenance',required='A native firmware capture is required; synthetic patterns remain bench inputs.'))
        if candidate is None:report['blockers'].append(dict(id='candidate-selection',required='An explicit bounded transformer candidate is required; none is selected automatically.'))
        # Assembly eligibility alone can never imply that a solver has run.
        report['blockers'].append(dict(id='connected-solver',required='Implement the assembled electrical/thermal solver and numerical acceptance before rendering.'))
        report['status']='blocked';save();return report
    except (ValueError,OSError,RuntimeError,subprocess.SubprocessError) as error:
        report['failure']=str(error);save();raise


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--capture',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--profile',default='k7222-11');p.add_argument('--candidate')
    p.add_argument('--fields',type=int,default=1);p.add_argument('--pre-roll-fields',type=int,default=1)
    p.add_argument('--mode',choices=('preflight','steady-supply-frame'),default='preflight')
    p.add_argument('--runtime',type=Path)
    p.add_argument('--linear-solver',choices=('sparse','klu'),default='sparse')
    p.add_argument('--reltol',type=float,default=.005)
    p.add_argument('--abstol',type=float,default=1e-6)
    p.add_argument('--max-step-ns',type=float,default=100)
    p.add_argument('--initial-voltage',action='append',default=[],metavar='NODE=VOLTS',help='Bounded warm starting guesses, not restored circuit state')
    p.add_argument('--electrical-cache',type=Path,default=Path('build/monitor/electrical-cache'),help='Verified completed traces, never simulator checkpoints')
    p.add_argument('--yoke-profile',type=Path,help='Frozen yoke hypothesis; defaults to the geometry-derived cosine-sheet model')
    p.add_argument('--magnetic-parameters',type=Path,help='Explicit bounded T3 parameter hypothesis')
    p.add_argument('--calibration-freeze',type=Path,help='Verified synthetic-grid calibration record; required before native rendering')
    p.add_argument('--wall-budget-hours',type=float,default=12)
    p.add_argument('--parameter',action='append',default=[],metavar='NAME=VALUE',help='Bounded steady-supply parameter override')
    p.add_argument('--sustained',action='store_true',help='Require 16 unchanged fields and at least 7 decay constants of original pre-roll')
    a=p.parse_args()
    if a.mode=='steady-supply-frame':
        if a.runtime is None:p.error('--runtime is required for steady-supply-frame')
        if a.profile!='k7222-11':p.error('unsupported steady-supply profile')
        import steady_supply
        changes={}
        for item in a.parameter:
            key,value=item.split('=',1);changes[key]=float(value)
        r=steady_supply.run(a.capture,a.output,a.runtime,candidate=a.candidate or 'auto',wall_budget_hours=a.wall_budget_hours,changes=changes,magnetic_parameters=a.magnetic_parameters,yoke_path=a.yoke_profile,electrical_cache=a.electrical_cache,calibration_freeze=a.calibration_freeze,
            solver=dict(linear_solver=a.linear_solver,reltol=a.reltol,abstol=a.abstol,max_step_s=a.max_step_ns/1e9,
                initial_voltages={k:float(v) for k,v in (item.split('=',1) for item in a.initial_voltage)}))
        print(json.dumps(dict(status=r['status'],blockers=r['blockers']),indent=2));raise SystemExit(2)
    r=run(a.capture,a.output,profile=a.profile,candidate=a.candidate,fields=a.fields,pre_roll_fields=a.pre_roll_fields,sustained=a.sustained)
    print(json.dumps(dict(status=r['status'],blockers=r['blockers']),indent=2));raise SystemExit(2)
