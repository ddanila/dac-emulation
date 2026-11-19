"""Strict ordered acceptance gates for the planned single native CRT frame.

Every gate needs explicit measured evidence. A missing report fails closed; the
nonblocking accounting observations cannot compensate for a failed gate.
"""
import argparse
import gzip
import hashlib
import json
import math
from pathlib import Path
import tempfile

import calibration_contract
import calibration_measurements
import inventory_audit
import phase_a_review
import periodic_frame
import readability_score
import scan_diagnostics
import service_score as service_scoring
import steady_acceptance
import steady_supply
import steady_trace

PERIODIC=('eht','horizontal_yoke_current','vertical_yoke_current','g2','g4','core_flux')
PERIODIC_PROBES={'eht':'v(eht)','horizontal_yoke_current':'i(lhorizontal)',
                 'vertical_yoke_current':'i(lvertical)','g2':'v(g2)','g4':'v(g4)',
                 'core_flux':'v(x1136.xshared.flux_b)'}
HELD_OUT=calibration_contract.HELD_OUT_POINTS
NATIVE_ARCHIVE=Path(__file__).resolve().parent/'examples/phase-a-native-full-text'


def finite(value):return type(value) in (int,float) and math.isfinite(value)


def point_status(score,n):
    return next((p.get('status') for p in score.get('points',[]) if p.get('test_point')==n),None)


def point_shape_status(score,n):
    return next((p.get('shape_status') for p in score.get('points',[]) if p.get('test_point')==n),None)


def verify_service_score(score):
    source=Path(score.get('input',''))
    window=score.get('requested_window_s')
    required=score.get('required_points')
    if not source.is_file() or not isinstance(window,list) or len(window)!=2 or not isinstance(required,list):
        raise ValueError('service score source or measurement window is missing')
    reproduced=service_scoring.score(source,start=window[0],end=window[1],
        required=required,probe_manifest=score.get('probe_manifest'),stimulus=score.get('stimulus'))
    if calibration_contract.digest(reproduced)!=calibration_contract.digest(score):
        raise ValueError('service score differs from the electrical trace')
    return True


def verify_source_review(evidence, *, ocr_root, source_pdf, marks_path):
    """Recompute the A1 prerequisite from the current source and agent readings."""
    ocr_root=Path(ocr_root);source_pdf=Path(source_pdf);marks_path=Path(marks_path)
    if not ocr_root.is_dir() or not marks_path.is_file() or not source_pdf.is_file():
        raise ValueError('A1 source review inputs are missing')
    for page in inventory_audit.PAGES:
        for tag in ('primary','r300','alt','cropL','cropR','struct'):
            suffix='' if tag=='primary' else '.'+tag
            if not (ocr_root/f'page_{page:03d}{suffix}.csv').is_file():
                raise ValueError('A1 OCR pass or table source is missing')
    source_sha=hashlib.sha256(source_pdf.read_bytes()).hexdigest()
    if source_sha!=phase_a_review.source_hash():
        raise ValueError('A1 source PDF differs from sources.json')
    inventory_raw=inventory_audit.INVENTORY.read_bytes()
    inventory=json.loads(inventory_raw)
    audit=inventory_audit.audit(inventory,ocr_root)
    marks_raw=marks_path.read_bytes()
    actual=phase_a_review.evaluate(inventory,audit,json.loads(marks_raw))
    actual.update(source_pdf_sha256=source_sha,
                  inventory_sha256=hashlib.sha256(inventory_raw).hexdigest(),
                  kicad_tree_sha256=phase_a_review.kicad_tree_hash(),
                  ocr_audit_sha256=phase_a_review.digest(audit),
                  marks_sha256=hashlib.sha256(marks_raw).hexdigest())
    if 'source_review' in evidence and evidence['source_review']!=actual:
        raise ValueError('reported A1 review differs from the current sources and marks')
    evidence['source_review']=actual
    return actual


def source_review_passes(review):
    if not isinstance(review,dict):return False
    count=review.get('machine_confirmed');resolved=review.get('agent_resolved')
    excluded=review.get('converter_only_unresolved')
    return (review.get('format')=='dac-monitor-phase-a-source-review-gate-v2'
            and review.get('passed') is True
            and review.get('inventory_entries')==260
            and type(count) is int and type(resolved) is int
            and count>=0 and resolved>=0 and count+resolved<=260
            and isinstance(excluded,list) and len(excluded)==260-count-resolved
            and set(excluded)<=phase_a_review.converter_only_ids()
            and review.get('frame_path_open_parts')==[]
            and review.get('open_parts')==[] and review.get('open_schematics')==[]
            and review.get('source_pdf_sha256')==phase_a_review.source_hash()
            and review.get('kicad_tree_sha256')==phase_a_review.kicad_tree_hash()
            and review.get('inventory_sha256')==hashlib.sha256(
                inventory_audit.INVENTORY.read_bytes()).hexdigest()
            and all(isinstance(review.get(key),str) and len(review[key])==64
                    for key in ('ocr_audit_sha256','marks_sha256')))


def verify_current_assembly_schematics(metadata):
    """Bind the reviewed KiCad tree to the actual ideal-rail circuit trial."""
    archived=metadata.get('experiment',{}).get('assembly_hashes',{})
    if not isinstance(archived,dict):
        raise ValueError('electrical trial lacks archived schematic hashes')
    for name,_,_ in steady_supply.assembly_sheets():
        path=steady_supply.ROOT/'circuits'/name
        key='circuits/'+name
        if not path.is_file() or archived.get(key)!=hashlib.sha256(path.read_bytes()).hexdigest():
            raise ValueError('electrical trial uses a stale or missing assembled schematic: '+name)
    return True


def verify_native_capture(evidence, score):
    """Bind the final electrical trial to the archived full-text native source."""
    manifest=json.loads((NATIVE_ARCHIVE/'manifest.json').read_text())
    compressed=(NATIVE_ARCHIVE/'capture.json.gz').read_bytes()
    if hashlib.sha256(compressed).hexdigest()!=manifest['compressed_sha256']:
        raise ValueError('native full-text archive changed')
    raw=gzip.decompress(compressed)
    capture_hash=hashlib.sha256(raw).hexdigest()
    if (capture_hash!=manifest['capture_sha256']
            or capture_hash!=evidence.get('native_capture_sha256')
            or hashlib.sha256((NATIVE_ARCHIVE/'logical-reference.png').read_bytes()).hexdigest()
               !=manifest['logical_reference_sha256']):
        raise ValueError('native full-text capture or logical reference mismatch')
    capture=json.loads(raw)
    if (capture.get('qualification')!='schematic-derived-logical'
            or capture.get('input_sha256')!=manifest['input_sha256']):
        raise ValueError('native full-text capture provenance mismatch')
    selected=steady_supply.select(capture)
    if (selected['status']!='complete'
            or selected['source_content_sha256']!=manifest['source_content_sha256']
            or selected['period_ticks']!=manifest['period_ticks']
            or selected['line_period_ticks']!=manifest['line_period_ticks']):
        raise ValueError('native full-text selected field mismatch')
    source,_=scan_diagnostics.source_summary(selected)
    if len(source['active_lines'])!=manifest.get('active_lines') or len(source['active_lines'])<100:
        raise ValueError('native full-text screen coverage mismatch')
    trace=Path(score.get('input',''))
    if trace.name!='trace.raw' or not trace.is_file():
        raise ValueError('native frame requires a connected trial trace')
    metadata_path=trace.with_name('metadata.json')
    if not metadata_path.is_file():
        raise ValueError('native frame trial metadata is missing')
    metadata=json.loads(metadata_path.read_text())
    experiment=metadata.get('experiment',{})
    if (experiment.get('capture_sha256')!=capture_hash
            or experiment.get('source_content_sha256')!=selected['source_content_sha256']
            or experiment.get('source_kind')!='schematic-derived-logical'):
        raise ValueError('electrical trial uses a different native source')
    verify_current_assembly_schematics(metadata)
    return selected,metadata


def verify_settling_evidence(evidence,score,selection,metadata):
    """Recompute G1, G1b and G2 from the final connected electrical trace."""
    actual=steady_supply.assess(Path(score['input']),metadata,selection)
    if 'settling' in evidence and evidence['settling']!=actual:
        raise ValueError('reported settling differs from the electrical trace')
    lock=actual['native_sync_lock']
    if 'horizontal_lock' in evidence and evidence['horizontal_lock']!=lock:
        raise ValueError('reported horizontal lock differs from the electrical trace')
    periodic=dict(fields=3 if actual['complete'] else None,
                  relative_errors={name:actual['waveform_relative_rms_error'].get(probe)
                                   for name,probe in PERIODIC_PROBES.items()})
    if 'periodicity' in evidence and evidence['periodicity']!=periodic:
        raise ValueError('reported periodicity differs from the electrical trace')
    evidence['settling']=actual
    evidence['horizontal_lock']=lock
    evidence['periodicity']=periodic
    return actual


def _completed_variant(path):
    path=Path(path)
    if path.name!='trace.raw' or not path.is_file():
        raise ValueError('G6 variant requires a completed trace.raw')
    directory=path.parent
    metadata=json.loads((directory/'metadata.json').read_text())
    solved=json.loads((directory/'solve.json').read_text())
    with (directory/'run.cir').open('rb') as stream:
        deck_sha=hashlib.file_digest(stream,'sha256').hexdigest()
    if (solved.get('status')!='complete' or solved.get('deck_sha256')!=deck_sha
            or metadata.get('experiment',{}).get('deck_sha256')!=deck_sha):
        raise ValueError('G6 variant deck or solve receipt mismatch')
    return metadata


def verify_electrical_refinement(evidence,score,base_metadata):
    """Recompute both G6 comparisons from separate completed solver trials."""
    claimed=evidence.get('electrical_refinement',{})
    paths={name:claimed.get(name+'_trace') for name in ('half_timestep','second_initialization')}
    if any(not isinstance(path,str) or not path for path in paths.values()):
        raise ValueError('G6 requires both variant trace paths')
    base_path=Path(score['input'])
    if not base_path.is_file() or base_path.name!='trace.raw':
        raise ValueError('G6 requires the scored connected trial trace')
    base_step=base_metadata.get('max_step_s')
    if not finite(base_step) or base_step<=0:
        raise ValueError('G6 base timestep is invalid')
    result={}
    for name,path in paths.items():
        variant_path=Path(path)
        if variant_path.resolve()==base_path.resolve() or any(
                variant_path.resolve()==Path(other).resolve() for other_name,other in paths.items()
                if other_name!=name):
            raise ValueError('G6 requires distinct completed trials')
        metadata=_completed_variant(variant_path)
        if (metadata.get('period_s')!=base_metadata.get('period_s')
                or metadata.get('simulated_fields')!=base_metadata.get('simulated_fields')
                or metadata.get('source_kind')!=base_metadata.get('source_kind')
                or metadata.get('candidate')!=base_metadata.get('candidate')
                or metadata.get('parameters')!=base_metadata.get('parameters')
                or metadata.get('yoke')!=base_metadata.get('yoke')
                or any(metadata.get('experiment',{}).get(key)!=base_metadata.get('experiment',{}).get(key)
                       for key in ('capture_sha256','source_content_sha256','assembly_hashes'))):
            raise ValueError('G6 variant changes the source or circuit parameters')
        step=metadata.get('max_step_s')
        if not finite(step) or step<=0 or (name=='half_timestep' and step>base_step/2*(1+1e-9)) or (name=='second_initialization' and step>base_step):
            raise ValueError('G6 variant has the wrong timestep')
        if name=='second_initialization' and metadata.get('initial_voltage_guesses')==base_metadata.get('initial_voltage_guesses'):
            raise ValueError('G6 second trial repeats the same initialization')
        comparison=steady_acceptance.compare(base_path,variant_path,base_metadata)
        errors=comparison.get('relative_rms_error',{})
        if set(errors)!=set(steady_acceptance.NAMES) or not all(finite(value) and value>=0 for value in errors.values()):
            raise ValueError('G6 waveform comparison is incomplete')
        result[name+'_relative_error']=max(errors.values())
    computed=dict(half_timestep=True,second_initialization=True,
                  half_timestep_relative_error=result['half_timestep_relative_error'],
                  second_initialization_relative_error=result['second_initialization_relative_error'])
    for key,value in computed.items():
        if key in claimed:
            reported=claimed[key]
            agrees=(reported is value if isinstance(value,bool) else
                    finite(reported) and math.isclose(reported,value,rel_tol=1e-9,abs_tol=1e-12))
            if not agrees:
                raise ValueError('reported G6 refinement differs from completed trials')
    evidence['electrical_refinement']=claimed|computed
    return computed


def verify_optical_refinement(evidence,score,metadata):
    """Bind both G7 optical comparisons to a field exported from the scored trial."""
    claimed=evidence.get('optical_refinement',{})
    names=('base_archive','integration_archive','spatial_archive')
    if any(not isinstance(claimed.get(name),str) or not claimed[name] for name in names):
        raise ValueError('G7 requires the base and both refined optical archives')
    directories={name:Path(claimed[name]) for name in names}
    if len({path.resolve() for path in directories.values()})!=3:
        raise ValueError('G7 requires distinct optical archives')
    period=metadata.get('period_s');fields=metadata.get('simulated_fields')
    if not finite(period) or period<=0 or type(fields) is not int or fields<4:
        raise ValueError('G7 electrical field window is invalid')
    end=period*fields
    with tempfile.TemporaryDirectory(prefix='phase-a-optical-source-') as temporary:
        field=Path(temporary)/'field.csv'
        export=steady_trace.export(score['input'],field,start_s=end-period,end_s=end)
        with field.open('rb') as stream:
            field_sha=hashlib.file_digest(stream,'sha256').hexdigest()
        if (export.get('raw_sha256')!=score.get('input_sha256')
                or export.get('trace_sha256')!=field_sha):
            raise ValueError('G7 field export does not match the scored electrical trace')
        base=json.loads((directories['base_archive']/'frame.json').read_text())
        if base.get('hashes',{}).get('input.csv')!=field_sha:
            raise ValueError('G7 optical input differs from the scored electrical field')
    integration=periodic_frame.compare(directories['base_archive'],directories['integration_archive'])
    spatial=periodic_frame.compare(directories['base_archive'],directories['spatial_archive'],spatial=True)
    if (integration.get('scope')!='optical-integration-refinement'
            or spatial.get('scope')!='spatial-refinement'):
        raise ValueError('G7 optical comparison scope mismatch')
    errors=(integration.get('relative_l2_error'),spatial.get('relative_l2_error'))
    if not all(finite(value) and value>=0 for value in errors):
        raise ValueError('G7 optical comparison error is invalid')
    computed=dict(integration_verified=integration.get('accepted') is True,
                  spatial_verified=spatial.get('accepted') is True,
                  integration_relative_error=errors[0],spatial_relative_error=errors[1],
                  relative_error=max(errors))
    for key,value in computed.items():
        if key in claimed:
            reported=claimed[key]
            agrees=(reported is value if isinstance(value,bool) else
                    finite(reported) and math.isclose(reported,value,rel_tol=1e-9,abs_tol=1e-12))
            if not agrees:
                raise ValueError('reported G7 refinement differs from optical archives')
    evidence['optical_refinement']=claimed|computed
    return computed


def verify_readability(evidence,selection):
    """Recompute G8 from the same unmodified optical archive used for G7."""
    archive=evidence.get('optical_refinement',{}).get('base_archive')
    if not isinstance(archive,str) or not archive:
        raise ValueError('G8 requires the G7 base optical archive')
    claimed=evidence.get('readability',{})
    computed=readability_score.score(selection,archive)
    computed['logical_capture_sha256']=evidence.get('native_capture_sha256')
    for key in ('source_kind','source_content_sha256','logical_capture_sha256',
                'one_global_affine_fit','fit_applied_to_render','correlation'):
        if key in claimed:
            expected=computed[key];reported=claimed[key]
            agrees=(math.isclose(reported,expected,rel_tol=1e-9,abs_tol=1e-12)
                    if key=='correlation' and finite(reported) else reported==expected)
            if not agrees:raise ValueError('reported G8 readability differs from the optical frame')
    evidence['readability']=claimed|computed
    return computed


def verify_calibration_measurements(evidence, score):
    """Recompute native-frame G3 electrical quantities before gate evaluation."""
    reported=evidence.get('calibration_measurements',{})
    if not isinstance(reported,dict) or not all(finite(reported.get(k)) for k in ('eht_v','horizontal_retrace_us')):
        return False
    if reported.get('electrical_trace_sha256')!=score.get('input_sha256'):
        raise ValueError('calibration measurements belong to a different electrical trace')
    path=Path(score.get('input',''))
    window=score.get('requested_window_s')
    if path.name!='trace.raw' or not path.is_file() or not isinstance(window,list) or len(window)!=2:
        raise ValueError('G3 calibration measurements require a connected final-field trace')
    actual=calibration_measurements.measure(path,start_s=window[0],end_s=window[1],line_s=62.5e-6)
    if (not math.isclose(reported['eht_v'],actual['eht_mean_v'],rel_tol=.001,abs_tol=1.)
            or not math.isclose(reported['horizontal_retrace_us'],actual['horizontal_retrace_us'],
                                rel_tol=.01,abs_tol=.5)):
        raise ValueError('G3 calibration measurements differ from the electrical trace')
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
    review=evidence.get('source_review',{})
    reviewed=source_review_passes(review)
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
    measured=evidence.get('calibration_measurements',{})
    geometry=evidence.get('grid_geometry',{})
    frozen_geometry=freeze.get('calibration_trial',{}).get('grid_geometry',{})
    geometry_matches_freeze=(geometry.get('electrical_trace_sha256')==freeze['calibration_trial']['trace_sha256']
        and all(finite(geometry.get(k)) and finite(frozen_geometry.get(k))
                and math.isclose(geometry[k],frozen_geometry[k],rel_tol=1e-9,abs_tol=1e-9)
                for k in ('picture_width_mm','picture_height_mm','horizontal_linearity','vertical_linearity')))
    calibration_sources_match=(score_is_for_trace
        and measured.get('electrical_trace_sha256')==trace_hash
        and geometry.get('source_capture_sha256')==freeze.get('source_capture_sha256')
        and geometry_matches_freeze)
    add('G3',score_is_for_trace
        and all(point_status(service_score,n)=='pass-numeric' for n in calibration_contract.CALIBRATION_POINTS)
        and all(point_shape_status(service_score,n)=='pass' for n in calibration_contract.CALIBRATION_POINTS)
        and calibration_sources_match
        and finite(measured.get('eht_v')) and 11000<=measured['eht_v']<=12000
        and finite(measured.get('horizontal_retrace_us')) and 12.8<=measured['horizontal_retrace_us']<=19.2
        and finite(geometry.get('picture_width_mm')) and 168<=geometry['picture_width_mm']<=252
        and finite(geometry.get('picture_height_mm')) and 116<=geometry['picture_height_mm']<=174,
        {'calibration_points':sorted(calibration_contract.CALIBRATION_POINTS),'targets':calibrated,
         'measured':measured,'grid_geometry':geometry,
         'measurement_sources_match':calibration_sources_match,
         'shape_failures':[n for n in sorted(calibration_contract.CALIBRATION_POINTS)
                           if point_shape_status(service_score,n)!='pass'],
         'service_score_matches_trace':score_is_for_trace})
    misses={n:{'numeric':point_status(service_score,n),'shape':point_shape_status(service_score,n)}
            for n in sorted(HELD_OUT)
            if point_status(service_score,n)!='pass-numeric' or point_shape_status(service_score,n)!='pass'}
    explanations=evidence.get('held_out_explanations',{})
    unexplained=[n for n in misses if not isinstance(explanations,dict)
                 or not isinstance(explanations.get(str(n)),str)
                 or not explanations[str(n)].strip()]
    add('G4',score_is_for_trace and len(misses)<=3 and not unexplained,
        {'misses':misses,'explanations':explanations,'unexplained':unexplained,
         'maximum_explained_misses':3})
    add('G5',geometry_matches_freeze
        and geometry.get('source_kind')=='synthetic-test-pattern'
        and geometry.get('source_capture_sha256')==freeze.get('source_capture_sha256')
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
    add('G7',optical.get('integration_verified') is True and optical.get('spatial_verified') is True
        and finite(optical.get('relative_error')) and 0<=optical['relative_error']<=.02,optical)
    readability=evidence.get('readability',{})
    add('G8',readability.get('source_kind')=='native-firmware-logical-timing-reference'
        and isinstance(evidence.get('native_capture_sha256'),str)
        and readability.get('logical_capture_sha256')==evidence['native_capture_sha256']
        and readability.get('one_global_affine_fit') is True
        and readability.get('fit_applied_to_render') is False
        and finite(readability.get('correlation')) and .7<=readability['correlation']<=1.,readability)
    reported={k:evidence.get(k) for k in ('signed_energy_ledger','interception_feedback',
                                          'heater_heat_balance','solver_step_audit')}
    return dict(format='dac-monitor-phase-a-gates-v1',accepted=reviewed and all(g['passed'] for g in results),
                prerequisite_a1=dict(passed=reviewed,review=review),
                blocking=results,reported_nonblocking=reported,
                full_monitor_qualified=False,specimen_validated=False)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence',type=Path,required=True)
    parser.add_argument('--service-score',type=Path,required=True)
    parser.add_argument('--calibration-freeze',type=Path,required=True)
    parser.add_argument('--source-review-ocr-root',type=Path,required=True)
    parser.add_argument('--source-review-pdf',type=Path,required=True)
    parser.add_argument('--source-review-marks',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    score=json.loads(args.service_score.read_text())
    verify_service_score(score)
    evidence=json.loads(args.evidence.read_text())
    verify_source_review(evidence,ocr_root=args.source_review_ocr_root,
                         source_pdf=args.source_review_pdf,
                         marks_path=args.source_review_marks)
    selection,metadata=verify_native_capture(evidence,score)
    verify_settling_evidence(evidence,score,selection,metadata)
    verify_calibration_measurements(evidence,score)
    verify_electrical_refinement(evidence,score,metadata)
    verify_optical_refinement(evidence,score,metadata)
    verify_readability(evidence,selection)
    result=evaluate(evidence,score,
                    json.loads(args.calibration_freeze.read_text()))
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    print('A1','PASS' if result['prerequisite_a1']['passed'] else 'FAIL')
    for gate in result['blocking']:print(gate['gate'],'PASS' if gate['passed'] else 'FAIL')
    return 0 if result['accepted'] else 2


if __name__=='__main__':raise SystemExit(main())
