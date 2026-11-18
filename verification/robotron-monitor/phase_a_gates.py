"""Strict ordered acceptance gates for the planned single native CRT frame.

Every gate needs explicit measured evidence. A missing report fails closed; the
nonblocking accounting observations cannot compensate for a failed gate.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path

import calibration_contract
import service_score as service_scoring

PERIODIC=('eht','horizontal_yoke_current','vertical_yoke_current','g2','g4','core_flux')
PERIODIC_PROBES={'eht':'v(eht)','horizontal_yoke_current':'i(lhorizontal)',
                 'vertical_yoke_current':'i(lvertical)','g2':'v(g2)','g4':'v(g4)',
                 'core_flux':'v(x1136.xshared.flux_b)'}
HELD_OUT=calibration_contract.HELD_OUT_POINTS


def finite(value):return type(value) in (int,float) and math.isfinite(value)


def point_status(score,n):
    return next((p.get('status') for p in score.get('points',[]) if p.get('test_point')==n),None)


def waveform_reviewed(evidence, n):
    review=evidence.get('waveform_reviews',{}).get(str(n),{})
    return (review.get('shape')=='agrees' and review.get('operating_conditions')=='agrees'
            and isinstance(review.get('reviewer'),str) and bool(review['reviewer'].strip()))


def verify_service_score(score):
    source=Path(score.get('input',''))
    window=score.get('requested_window_s')
    required=score.get('required_points')
    if not source.is_file() or not isinstance(window,list) or len(window)!=2 or not isinstance(required,list):
        raise ValueError('service score source or measurement window is missing')
    reproduced=service_scoring.score(source,start=window[0],end=window[1],required=required)
    if calibration_contract.digest(reproduced)!=calibration_contract.digest(score):
        raise ValueError('service score differs from the electrical trace')
    return True


def evaluate(evidence,service_score,freeze):
    if evidence.get('format')!='dac-monitor-phase-a-gate-evidence-v1':raise ValueError('invalid evidence format')
    if service_score.get('format')!='dac-monitor-service-score-v1':raise ValueError('invalid service score')
    register_hash=hashlib.sha256(service_scoring.REGISTER.read_bytes()).hexdigest()
    if service_score.get('register_sha256')!=register_hash:
        raise ValueError('service score does not use the current manual register')
    point_numbers=[p.get('test_point') for p in service_score.get('points',[])]
    if len(point_numbers)!=17 or set(point_numbers)!=set(range(1,18)):
        raise ValueError('service score must contain each manual test point exactly once')
    calibration_contract.verify(freeze)
    trace_hash=evidence.get('electrical_trace_sha256')
    score_is_for_trace=(isinstance(trace_hash,str) and len(trace_hash)==64
                        and trace_hash==service_score.get('input_sha256'))
    results=[]
    def add(name,passed,detail):results.append(dict(gate=name,passed=bool(passed),detail=detail))
    settling=evidence.get('settling',{})
    lock=evidence.get('horizontal_lock') or settling.get('native_sync_lock',{})
    counts=[lock.get(k) for k in ('reference_edges','flybacks_in_window','matched_edges')]
    add('G1',all(type(x) is int and x>0 for x in counts) and len(set(counts))==1
        and finite(lock.get('phase_variation_lines')) and lock['phase_variation_lines']<=.01
        and lock.get('missing_edges')==0 and lock.get('reused_flybacks')==0
        and lock.get('unmatched_flybacks')==0
        and lock.get('fields')==3,lock)
    jitter=lock.get('maximum_adjacent_jitter_s')
    add('G1b',finite(jitter) and 0<=jitter<=36e-9,{'maximum_adjacent_jitter_s':jitter,'limit_s':36e-9})
    periodic=evidence.get('periodicity')
    if periodic is None and settling:
        original=settling.get('waveform_relative_rms_error',{})
        periodic={'fields':3 if settling.get('complete') else None,
                  'relative_errors':{name:original.get(probe) for name,probe in PERIODIC_PROBES.items()}}
    periodic=periodic or {}
    values=periodic.get('relative_errors',{})
    add('G2',periodic.get('fields')==3 and all(finite(values.get(k)) and 0<=values[k]<=.01 for k in PERIODIC),
        {'fields':periodic.get('fields'),'relative_errors':values,'required':PERIODIC})
    calibrated=freeze.get('targets',{})
    add('G3',score_is_for_trace
        and all(point_status(service_score,n)=='pass-numeric' for n in calibration_contract.CALIBRATION_POINTS)
        and all(waveform_reviewed(evidence,n) for n in calibration_contract.CALIBRATION_POINTS)
        and all(finite(calibrated.get(k)) for k in ('eht_v','horizontal_retrace_us','picture_width_mm','picture_height_mm'))
        and 11000<=calibrated['eht_v']<=12000
        and 12.8<=calibrated['horizontal_retrace_us']<=19.2
        and 168<=calibrated['picture_width_mm']<=252
        and 116<=calibrated['picture_height_mm']<=174,
        {'calibration_points':sorted(calibration_contract.CALIBRATION_POINTS),'targets':calibrated,
         'unreviewed_waveforms':[n for n in sorted(calibration_contract.CALIBRATION_POINTS)
                                 if not waveform_reviewed(evidence,n)],
         'service_score_matches_trace':score_is_for_trace})
    misses={n:point_status(service_score,n) for n in sorted(HELD_OUT) if point_status(service_score,n)!='pass-numeric'}
    explanations=evidence.get('held_out_explanations',{})
    unreviewed=[n for n in sorted(HELD_OUT) if not waveform_reviewed(evidence,n)]
    add('G4',score_is_for_trace and not misses and not unreviewed,
        {'misses':misses,'unreviewed_waveforms':unreviewed,'explanations':explanations,
                         'unexplained':[n for n in misses if str(n) not in explanations]})
    geometry=evidence.get('grid_geometry',{})
    add('G5',geometry.get('source_kind')=='synthetic-test-pattern'
        and all(finite(geometry.get(k)) for k in ('picture_width_mm','picture_height_mm','horizontal_linearity','vertical_linearity'))
        and .9<=geometry['picture_width_mm']/210<=1.05
        and .9<=geometry['picture_height_mm']/145<=1.05
        and 0<=geometry['horizontal_linearity']<=.1
        and 0<=geometry['vertical_linearity']<=.1,geometry)
    refinement=evidence.get('electrical_refinement',{})
    add('G6',refinement.get('half_timestep') is True and refinement.get('second_initialization') is True
        and all(finite(refinement.get(k)) and 0<=refinement[k]<=.01
                for k in ('half_timestep_relative_error','second_initialization_relative_error')),refinement)
    optical=evidence.get('optical_refinement',{})
    add('G7',finite(optical.get('relative_error')) and 0<=optical['relative_error']<=.02,optical)
    readability=evidence.get('readability',{})
    add('G8',readability.get('source_kind')=='native-firmware-logical-timing-reference'
        and isinstance(evidence.get('native_capture_sha256'),str)
        and readability.get('logical_capture_sha256')==evidence['native_capture_sha256']
        and readability.get('one_global_affine_fit') is True
        and readability.get('fit_applied_to_render') is False
        and finite(readability.get('correlation')) and .7<=readability['correlation']<=1.,readability)
    reported={k:evidence.get(k) for k in ('signed_energy_ledger','interception_feedback',
                                          'heater_heat_balance','solver_step_audit')}
    return dict(format='dac-monitor-phase-a-gates-v1',accepted=all(g['passed'] for g in results),
                blocking=results,reported_nonblocking=reported,
                full_monitor_qualified=False,specimen_validated=False)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence',type=Path,required=True)
    parser.add_argument('--service-score',type=Path,required=True)
    parser.add_argument('--calibration-freeze',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    score=json.loads(args.service_score.read_text())
    verify_service_score(score)
    result=evaluate(json.loads(args.evidence.read_text()),score,
                    json.loads(args.calibration_freeze.read_text()))
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    for gate in result['blocking']:print(gate['gate'],'PASS' if gate['passed'] else 'FAIL')
    return 0 if result['accepted'] else 2


if __name__=='__main__':raise SystemExit(main())
