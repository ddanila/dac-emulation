"""Freeze bounded K7222 calibration before using a native frame.

The calibration observations are deliberately disjoint from the held-out
service points. This module records evidence; it never searches parameters.
"""
import argparse
import hashlib
import json
import math
import re
from pathlib import Path

import service_score
import reference
import steady_supply
import transformer_candidates
import yoke_geometry
import lab
import calibration_measurements
import grid_geometry

CALIBRATION_POINTS=frozenset((14,15,17))
HELD_OUT_POINTS=frozenset(range(1,18))-CALIBRATION_POINTS
ASSUMPTION_KEYS=frozenset(('t3_candidate','t3_winding_parameters','yoke_profile',
                           'l4_coupling','horizontal_tank_l'))
TRIM_KEYS=frozenset(('regulated_5v_r9','vertical_sync_r22','oscillator_t1',
                     'horizontal_hold_r24','dark_raster_r28',
                     'max_beam_r4_0126921','horizontal_linearity_l3',
                     'picture_width_r5','centering_horizontal_r4_0126931',
                     'height_r35','linearity_r60','linearity_r59',
                     'centering_vertical_r58','focus','brightness','contrast'))
TRIM_PROCEDURE_STEPS={
    'regulated_5v_r9':(1,), 'vertical_sync_r22':(3,),
    'oscillator_t1':(4,), 'horizontal_hold_r24':(5,),
    'dark_raster_r28':(2,6), 'max_beam_r4_0126921':(6,),
    'horizontal_linearity_l3':(8,), 'picture_width_r5':(8,),
    'centering_horizontal_r4_0126931':(8,), 'height_r35':(9,),
    'linearity_r60':(9,), 'linearity_r59':(9,),
    'centering_vertical_r58':(9,), 'focus':(),
    'brightness':(2,6,7), 'contrast':(6,),
}
# Most bindings follow source IDs in the assembled KiCad sheets. R5 and R4
# use the explicitly declared ideal-rail equivalents in steady_supply.py.
TRIM_PARAMETERS={
    'regulated_5v_r9':'reg5_position',
    'vertical_sync_r22':'vertical_trim',
    'oscillator_t1':'horizontal_tank_l',
    'horizontal_hold_r24':'horizontal_trim_fraction',
    'dark_raster_r28':'horizontal_brightness_fraction',
    'max_beam_r4_0126921':'contrast_trim',
    'horizontal_linearity_l3':'horizontal_linearity_l',
    'picture_width_r5':'width_r5_position',
    'centering_horizontal_r4_0126931':'centering_horizontal_r4_position',
    'height_r35':'height_trim',
    'linearity_r59':'linearity_r59',
    'linearity_r60':'linearity_r60',
    'centering_vertical_r58':'symmetry_fraction',
    'focus':'horizontal_focus_fraction',
    'contrast':'contrast_position',
}
SETTLING_PROBES=('v(eht)','v(g2)','v(g4)','v(cathode)',
                 'i(lhorizontal)','i(lvertical)','v(x1136.xshared.flux_b)')
T3_GRAPH='reference/k7222-11/t3-winding-hypothesis.json'


def _current_circuit_hashes():
    """Circuit sources whose changes invalidate an earlier grid calibration."""
    names=[T3_GRAPH]+['circuits/'+name for name,_,_ in steady_supply.assembly_sheets()]
    return {name:hashlib.sha256((steady_supply.ROOT/name).read_bytes()).hexdigest()
            for name in names}


def _settled(report):
    if not isinstance(report,dict):return False
    errors=report.get('waveform_relative_rms_error',{})
    return (report.get('format')=='dac-steady-supply-settling-v1'
            and report.get('complete') is True
            and report.get('accepted') is True
            and report.get('failures')==[]
            and isinstance(report.get('native_sync_lock'),dict)
            and report['native_sync_lock'].get('accepted') is True
            and isinstance(errors,dict)
            and all(type(errors.get(name)) in (int,float)
                    and math.isfinite(errors[name]) and 0<=errors[name]<.01
                    for name in SETTLING_PROBES))


def trim_record_template():
    """Blank control positions with the printed steps already identified."""
    result={control:dict(setting=None,procedure_steps=list(steps),observation=None)
            for control,steps in TRIM_PROCEDURE_STEPS.items()}
    result['focus']['criterion_source']={'file':'older-operation.pdf','page':6}
    return result


def _validate_trim_record(trims):
    """Identify the printed adjustment steps and observed basis for each trim."""
    if not isinstance(trims,dict) or set(trims)!=TRIM_KEYS or set(TRIM_PROCEDURE_STEPS)!=TRIM_KEYS:
        raise ValueError('missing or extra recorded trim')
    manual=json.loads(service_score.REGISTER.read_text())
    printed={item['step'] for item in manual['adjustment_procedure']}
    if printed!=set(range(1,11)):
        raise ValueError('manual adjustment procedure changed')
    for control,steps in TRIM_PROCEDURE_STEPS.items():
        item=trims[control]
        if (not isinstance(item,dict)
                or type(item.get('setting')) not in (int,float)
                or not math.isfinite(item['setting'])
                or item.get('procedure_steps')!=list(steps)
                or not set(steps)<=printed
                or not isinstance(item.get('observation'),str)
                or not item['observation'].strip()):
            raise ValueError('trim lacks setting, printed steps or observation: '+control)
        if control=='focus' and item.get('criterion_source')!={'file':'older-operation.pdf','page':6}:
            raise ValueError('focus trim lacks the manual page-6 criterion source')
    return True


def _validate_trim_bindings(trims, parameters, deck=None):
    """Reject recorded positions that were not applied to the connected deck."""
    bounds={name:(values[1],values[2]) for name,values in steady_supply.signal_path.BOUNDS.items()}
    bounds.update({name:(values[1],values[2]) for name,values in steady_supply.ASSEMBLY_BOUNDS.items()})
    for profile_name in ('horizontal-oscillator','vertical-output','regulator5'):
        profile=reference.read_profile(steady_supply.ROOT/'profiles'/('k7222-11-'+profile_name+'.json'))
        bounds.update({name:(entry['minimum'],entry['maximum'])
                       for name,entry in profile['parameters'].items()})
    declared=None
    if deck is not None:
        declared={name:float(value) for name,value in re.findall(
            r'^\.param\s+(\w+)=([^\s]+)\s*$',deck,re.M)}
    for control,parameter in TRIM_PARAMETERS.items():
        setting=trims.get(control,{}).get('setting')
        actual=parameters.get(parameter)
        if (type(setting) not in (int,float) or not math.isfinite(setting)
                or type(actual) not in (int,float) or not math.isfinite(actual)
                or parameter not in bounds or not bounds[parameter][0]<=setting<=bounds[parameter][1]
                or not math.isclose(setting,actual,rel_tol=1e-12,abs_tol=0)):
            raise ValueError('manual trim was not applied to connected model: '+control)
        if declared is not None and (parameter not in declared
                or not math.isclose(setting,declared[parameter],rel_tol=1e-12,abs_tol=0)):
            raise ValueError('manual trim was not applied to connected deck: '+control)
    unbound=sorted(TRIM_KEYS-set(TRIM_PARAMETERS))
    if unbound:raise ValueError('manual trims lack connected model binding: '+', '.join(unbound))
    return True


def digest(data):
    return hashlib.sha256(json.dumps(data,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def _identified_json(item, label):
    if not isinstance(item,dict) or set(item)!=set(('path','sha256')):
        raise ValueError('missing frozen '+label+' path and hash')
    path=Path(item['path'])
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=item['sha256']:
        raise ValueError(label+' file or hash mismatch')
    return json.loads(path.read_text())


def _validate_synthetic_capture(proposal):
    path=Path(proposal.get('source_capture_path',''))
    if not path.is_file():raise ValueError('synthetic calibration capture is missing')
    actual=hashlib.sha256(path.read_bytes()).hexdigest()
    if actual!=proposal.get('source_capture_sha256'):
        raise ValueError('synthetic calibration capture hash mismatch')
    capture=lab.parse_capture(path)
    if capture.get('qualification')!='synthetic-test-pattern' or capture.get('pattern') not in ('grid','crosshatch'):
        raise ValueError('calibration requires a labelled grid or crosshatch capture')
    selected=steady_supply.select(capture)
    if selected['status']!='complete':raise ValueError('synthetic calibration capture lacks repeated complete fields')
    period=selected['period_ticks'];line=selected['line_period_ticks']
    if period%line:raise ValueError('synthetic calibration capture has incomplete lines')
    if (not math.isclose(line/capture['clock_hz'],62.5e-6,rel_tol=0,abs_tol=1e-9)
            or not math.isclose(period/capture['clock_hz'],.0195,rel_tol=0,abs_tol=1e-9)):
        raise ValueError('synthetic calibration timing differs from native S550 mode')
    height=period//line;active=set()
    for a,b in zip(selected['events'],selected['events'][1:]+[[period,0,0,0]]):
        if a[1] and b[0]>a[0]:active.update(range(a[0]//line,(b[0]-1)//line+1))
    if not active or len(active)<.9*height or min(active)>.1*height or max(active)<.95*height:
        raise ValueError('synthetic calibration capture does not cover the full screen')
    return dict(pattern=capture['pattern'], period_s=period/capture['clock_hz'],
                line_s=line/capture['clock_hz'],
                clock_hz=capture['clock_hz'],selection=selected,
                source_content_sha256=selected['source_content_sha256'])


def _validate_calibration_trial(proposal, score, source):
    """Require a completed connected solve of this exact synthetic capture."""
    trace=Path(score.get('input','')).resolve()
    if trace.name!='trace.raw' or not trace.is_file():
        raise ValueError('calibration score must use a connected trace.raw')
    trial=trace.parent
    deck=trial/'run.cir';metadata_path=trial/'metadata.json';solve_path=trial/'solve.json'
    if not all(path.is_file() for path in (deck,metadata_path,solve_path)):
        raise ValueError('calibration trial lacks deck, metadata or solver receipt')
    metadata=json.loads(metadata_path.read_text())
    solved=json.loads(solve_path.read_text())
    deck_hash=hashlib.sha256(deck.read_bytes()).hexdigest()
    experiment=metadata.get('experiment',{})
    if (experiment.get('source_kind')!='synthetic-test-pattern'
            or metadata.get('source_kind')!='synthetic-test-pattern'
            or experiment.get('capture_sha256')!=proposal['source_capture_sha256']
            or experiment.get('source_content_sha256')!=source['source_content_sha256']):
        raise ValueError('calibration trial did not use the selected synthetic capture')
    if (experiment.get('deck_sha256')!=deck_hash or solved.get('deck_sha256')!=deck_hash
            or solved.get('status')!='complete' or solved.get('returncode')!=0
            or solved.get('timeout') is not False):
        raise ValueError('calibration trial deck or solver receipt is not complete')
    actual_candidate=metadata.get('candidate',{}).get('candidate',{}).get('id')
    if actual_candidate!=proposal['candidate_id']:
        raise ValueError('calibration trial used a different T3 candidate')
    actual_parameters=metadata.get('parameters',{})
    _validate_trim_bindings(proposal['trims'],actual_parameters,deck.read_text())
    for key in ('l4_coupling','horizontal_tank_l'):
        value=actual_parameters.get(key)
        if (type(value) not in (int,float) or not math.isfinite(value)
                or not math.isclose(value,proposal['assumptions'][key],rel_tol=1e-12,abs_tol=0)):
            raise ValueError('calibration trial used different '+key)
    hashes=experiment.get('assembly_hashes',{})
    circuit_hashes=_current_circuit_hashes()
    if not isinstance(hashes,dict) or any(hashes.get(name)!=sha
                                           for name,sha in circuit_hashes.items()):
        raise ValueError('calibration trial uses a stale T3 graph or assembled schematic')
    magnetic_hash=(hashes.get('magnetic-override.json') or
                   hashes.get('reference/k7222-11/t3-initial-parameters.json'))
    if (magnetic_hash!=proposal['assumptions']['t3_winding_parameters']['sha256']
            or hashes.get('profiles/yoke.json')!=proposal['assumptions']['yoke_profile']['sha256']):
        raise ValueError('calibration trial used different magnetic or yoke parameters')
    period=source['period_s'];fields=metadata.get('simulated_fields')
    if (type(fields) is not int or fields<4 or fields>64
            or type(metadata.get('period_s')) not in (int,float)
            or not math.isclose(metadata['period_s'],period,rel_tol=0,abs_tol=1e-9)):
        raise ValueError('calibration trial timing differs from synthetic capture')
    window=score.get('requested_window_s')
    if (not isinstance(window,list) or len(window)!=2
            or not all(type(t) in (int,float) and math.isfinite(t) for t in window)
            or not math.isclose(window[0],(fields-1)*period,rel_tol=0,abs_tol=1e-9)
            or not math.isclose(window[1],fields*period,rel_tol=0,abs_tol=1e-9)):
        raise ValueError('calibration score must cover the final complete grid field')
    settling=steady_supply.assess(trace,metadata,source['selection'])
    if not _settled(settling):
        raise ValueError('calibration grid trial is not locked and periodic')
    measurements=calibration_measurements.measure(trace,start_s=window[0],
        end_s=window[1],line_s=source['line_s'])
    return dict(trace_sha256=score['input_sha256'],deck_sha256=deck_hash,
                metadata_sha256=hashlib.sha256(metadata_path.read_bytes()).hexdigest(),
                solver_receipt_sha256=hashlib.sha256(solve_path.read_bytes()).hexdigest(),
                circuit_hashes=circuit_hashes,
                settling=settling,
                **measurements)


def freeze(proposal, score):
    if proposal.get('format')!='dac-monitor-calibration-proposal-v1':raise ValueError('invalid proposal format')
    if proposal.get('source_kind')!='synthetic-test-pattern':raise ValueError('calibration requires labelled synthetic grid')
    if proposal.get('fit_points')!=sorted(CALIBRATION_POINTS):raise ValueError('fit points must be exactly 14, 15 and 17')
    if proposal.get('image_used_for_selection') is not False:raise ValueError('rendered image must not select calibration values')
    if set(proposal.get('assumptions',{}))!=ASSUMPTION_KEYS:raise ValueError('missing or extra assumed parameter')
    _validate_trim_record(proposal.get('trims'))
    if not isinstance(proposal.get('source_capture_sha256'),str) or len(proposal['source_capture_sha256'])!=64:
        raise ValueError('missing capture identity')
    source=_validate_synthetic_capture(proposal)
    if not isinstance(proposal.get('candidate_id'),str) or not proposal['candidate_id']:
        raise ValueError('missing T3 candidate identity')
    if proposal['assumptions']['t3_candidate']!=proposal['candidate_id']:
        raise ValueError('T3 candidate mismatch')
    for key in ('l4_coupling','horizontal_tank_l'):
        value=proposal['assumptions'][key]
        if type(value) not in (int,float) or not math.isfinite(value):raise ValueError('invalid '+key)
    l4=steady_supply.ASSEMBLY_BOUNDS['l4_coupling']
    if not l4[1]<=proposal['assumptions']['l4_coupling']<=l4[2]:raise ValueError('L4 coupling outside declared bound')
    profile=reference.read_profile(steady_supply.ROOT/'profiles/k7222-11-horizontal-oscillator.json')
    tank=profile['parameters']['horizontal_tank_l']
    if not tank['minimum']<=proposal['assumptions']['horizontal_tank_l']<=tank['maximum']:
        raise ValueError('tank outside declared bound')
    magnetic=_identified_json(proposal['assumptions']['t3_winding_parameters'],'T3 parameters')
    yoke=_identified_json(proposal['assumptions']['yoke_profile'],'yoke profile')
    graph=json.loads((steady_supply.ROOT/T3_GRAPH).read_text())
    candidate=next((c for c in transformer_candidates.enumerate_candidates(graph) if c['id']==proposal['candidate_id']),None)
    if candidate is None:raise ValueError('unknown T3 candidate')
    transformer_candidates.compile_model(graph,candidate,magnetic,backend='flux')
    yoke_model=yoke_geometry.derive(yoke)
    if score.get('format')!='dac-monitor-service-score-v1' or score.get('register_sha256')!=hashlib.sha256(service_score.REGISTER.read_bytes()).hexdigest():
        raise ValueError('service score does not match current reference register')
    trial_evidence=_validate_calibration_trial(proposal,score,source)
    trial_evidence['grid_geometry']=grid_geometry.measure(Path(score['input']),
        source['selection'],source['clock_hz'],start_s=score['requested_window_s'][0],
        end_s=score['requested_window_s'][1],field=yoke_model['field'])
    input_path=Path(score.get('input',''))
    if not input_path.is_file():raise ValueError('calibration score input is missing')
    window=score.get('requested_window_s')
    if not isinstance(window,list) or len(window)!=2:raise ValueError('calibration score window is missing')
    reproduced=service_score.score(input_path,start=window[0],end=window[1],required=score.get('required_points',[]))
    if digest(reproduced)!=digest(score):raise ValueError('calibration score is not reproducible')
    points={p['test_point']:p for p in score.get('points',[])}
    if any(points.get(n,{}).get('status')!='pass-numeric' for n in CALIBRATION_POINTS):
        raise ValueError('calibration service points do not pass')
    targets=proposal.get('targets',{})
    if set(targets)!=set(('eht_v','horizontal_retrace_us','picture_width_mm','picture_height_mm')):
        raise ValueError('incomplete calibration targets')
    if not all(type(x) in (int,float) and math.isfinite(x) for x in targets.values()):
        raise ValueError('nonfinite calibration target')
    if not 11000<=targets['eht_v']<=12000:raise ValueError('high voltage outside 11–12 kV')
    if not 11000<=trial_evidence['eht_mean_v']<=12000:
        raise ValueError('measured EHT outside 11–12 kV')
    if not math.isclose(targets['eht_v'],trial_evidence['eht_mean_v'],rel_tol=.01,abs_tol=0):
        raise ValueError('proposed EHT differs from connected trace measurement')
    if not 16*.8<=targets['horizontal_retrace_us']<=16*1.2:raise ValueError('retrace outside manual ±20%')
    if not 12.8<=trial_evidence['horizontal_retrace_us']<=19.2:
        raise ValueError('measured retrace outside manual ±20%')
    if not math.isclose(targets['horizontal_retrace_us'],trial_evidence['horizontal_retrace_us'],rel_tol=.05,abs_tol=1.):
        raise ValueError('proposed retrace differs from connected trace measurement')
    if not 210*.8<=targets['picture_width_mm']<=210*1.2:raise ValueError('width outside manual ±20%')
    if not 145*.8<=targets['picture_height_mm']<=145*1.2:raise ValueError('height outside manual ±20%')
    geometry=trial_evidence['grid_geometry']
    for key,nominal in (('picture_width_mm',210),('picture_height_mm',145)):
        if (not nominal*.8<=geometry[key]<=nominal*1.2
                or not math.isclose(targets[key],geometry[key],rel_tol=.05,abs_tol=5.)):
            raise ValueError('proposed '+key+' differs from connected grid geometry')
    record=dict(format='dac-monitor-calibration-freeze-v1',source_kind='synthetic-test-pattern',
                source_capture_sha256=proposal['source_capture_sha256'],source_pattern=source['pattern'],
                candidate_id=proposal['candidate_id'],
                assumptions=proposal['assumptions'],trims=proposal['trims'],targets=targets,
                calibration_trial=trial_evidence,
                fit_points=sorted(CALIBRATION_POINTS),held_out_points=sorted(HELD_OUT_POINTS),
                calibration_score_sha256=digest(score),image_used_for_selection=False,
                full_monitor_qualified=False,specimen_validated=False)
    record['freeze_sha256']=digest(record)
    return record


def verify(record):
    if record.get('format')!='dac-monitor-calibration-freeze-v1':raise ValueError('invalid freeze format')
    check=dict(record);sha=check.pop('freeze_sha256',None)
    if sha!=digest(check):raise ValueError('calibration freeze changed')
    if check.get('fit_points')!=sorted(CALIBRATION_POINTS) or check.get('held_out_points')!=sorted(HELD_OUT_POINTS):
        raise ValueError('calibration and validation sets overlap or changed')
    if (check.get('source_kind')!='synthetic-test-pattern'
            or check.get('source_pattern') not in ('grid','crosshatch')
            or check.get('image_used_for_selection') is not False):
        raise ValueError('invalid calibration source or image selection')
    if set(check.get('assumptions',{}))!=ASSUMPTION_KEYS or set(check.get('trims',{}))!=TRIM_KEYS:
        raise ValueError('incomplete frozen assumptions or trims')
    _validate_trim_record(check['trims'])
    if check['assumptions']['t3_candidate']!=check.get('candidate_id'):
        raise ValueError('frozen candidate mismatch')
    if any(not isinstance(check.get(key),str) or len(check[key])!=64
           for key in ('source_capture_sha256','calibration_score_sha256')):
        raise ValueError('missing frozen evidence identity')
    trial=check.get('calibration_trial',{})
    hashes=('trace_sha256','deck_sha256','metadata_sha256','solver_receipt_sha256')
    if (set(trial)!=set((*hashes,'circuit_hashes','settling','eht_mean_v','horizontal_retrace_us',
                        'horizontal_yoke_swing_a','retrace_method','line_count','phase_bins','grid_geometry'))
            or any(not isinstance(trial.get(key),str) or len(trial[key])!=64 for key in hashes)
            or type(trial.get('eht_mean_v')) not in (int,float)
            or not math.isfinite(trial['eht_mean_v'])
            or type(trial.get('horizontal_retrace_us')) not in (int,float)
            or not math.isfinite(trial['horizontal_retrace_us'])
            or type(trial.get('horizontal_yoke_swing_a')) not in (int,float)
            or not math.isfinite(trial['horizontal_yoke_swing_a'])
            or trial.get('retrace_method')!='shorter-extrema-arc-of-line-averaged-yoke-current'
            or type(trial.get('line_count')) is not int or trial['line_count']<32
            or type(trial.get('phase_bins')) is not int or not 64<=trial['phase_bins']<=4096):
        raise ValueError('missing completed calibration trial identity')
    if trial['circuit_hashes']!=_current_circuit_hashes():
        raise ValueError('frozen calibration uses a stale T3 graph or assembled schematic')
    settling=trial['settling']
    if not _settled(settling):
        raise ValueError('frozen calibration grid is not locked and periodic')
    geometry=trial.get('grid_geometry',{})
    if (not isinstance(geometry,dict)
            or geometry.get('method')!='source-grid-markers-through-connected-electrodes-yoke-and-central-ray'
            or any(type(geometry.get(k)) not in (int,float) or not math.isfinite(geometry[k])
                   for k in ('picture_width_mm','picture_height_mm','horizontal_linearity',
                             'vertical_linearity','horizontal_center_mm','vertical_center_mm',
                             'beam_launch_peak_ua','beam_launch_emitting_fraction','beam_launch_marker_fraction',
                             'beam_launch_threshold_ua'))
            or geometry['beam_launch_threshold_ua']!=.01
            or geometry['beam_launch_peak_ua']<.05
            or not .005<=geometry['beam_launch_emitting_fraction']<=1.
            or not .1<=geometry['beam_launch_marker_fraction']<=1.
            or any(type(geometry.get(k)) is not int or geometry[k]<5
                   for k in ('stripe_rows','horizontal_marker_rows','marker_count'))):
        raise ValueError('missing measured grid geometry')
    targets=check.get('targets',{})
    if (set(targets)!=set(('eht_v','horizontal_retrace_us','picture_width_mm','picture_height_mm'))
        or not all(type(value) in (int,float) and math.isfinite(value) for value in targets.values())
        or not 11000<=targets['eht_v']<=12000
        or not 12.8<=targets['horizontal_retrace_us']<=19.2
        or not 168<=targets['picture_width_mm']<=252
        or not 116<=targets['picture_height_mm']<=174):
        raise ValueError('invalid frozen calibration target')
    if (not 11000<=trial['eht_mean_v']<=12000
            or not math.isclose(targets['eht_v'],trial['eht_mean_v'],rel_tol=.01,abs_tol=0)
            or not 12.8<=trial['horizontal_retrace_us']<=19.2
            or not math.isclose(targets['horizontal_retrace_us'],trial['horizontal_retrace_us'],rel_tol=.05,abs_tol=1.)):
        raise ValueError('frozen EHT or retrace differs from measured calibration trial')
    if any(not nominal*.8<=geometry[key]<=nominal*1.2
           or not math.isclose(targets[key],geometry[key],rel_tol=.05,abs_tol=5.)
           for key,nominal in (('picture_width_mm',210),('picture_height_mm',145))):
        raise ValueError('frozen picture size differs from measured calibration trial')
    return True


def verify_run(record, *, candidate_id, parameters, magnetic_sha256, yoke_sha256):
    """Bind a connected solve to the assumptions chosen on the synthetic grid."""
    verify(record)
    _validate_trim_bindings(record['trims'],parameters)
    assumptions=record['assumptions']
    if candidate_id!=record['candidate_id']:
        raise ValueError('connected T3 candidate differs from calibration freeze')
    for name, actual in (('t3_winding_parameters',magnetic_sha256),
                         ('yoke_profile',yoke_sha256)):
        source=assumptions[name]
        if not isinstance(source,dict) or source.get('sha256')!=actual:
            raise ValueError('connected '+name+' differs from calibration freeze')
    for name in ('l4_coupling','horizontal_tank_l'):
        expected=assumptions[name]
        actual=parameters.get(name)
        if not (type(actual) in (int,float) and math.isfinite(actual)
                and math.isclose(actual,expected,rel_tol=1e-12,abs_tol=0)):
            raise ValueError('connected '+name+' differs from calibration freeze')
    return True


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--proposal',type=Path,required=True)
    parser.add_argument('--service-score',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    record=freeze(json.loads(args.proposal.read_text()),json.loads(args.service_score.read_text()))
    verify(record)
    with args.output.open('x') as stream:stream.write(json.dumps(record,indent=2)+'\n')
    print(record['freeze_sha256'])


if __name__=='__main__':main()
