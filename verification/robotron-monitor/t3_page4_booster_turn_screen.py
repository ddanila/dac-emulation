"""Probe source-visible booster tap sections in the conditional 20-port stage."""

import argparse
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

import page4_t3_visible_wrapper as wrapper
import t3_brimar_boost_boundary_screen as boost
import t3_output_stage_sweep as stage
import t3_page4_visible_stage_screen as visible
import transformer_candidates as tc


ROOT = Path(__file__).resolve().parent
REF = ROOT / 'reference/k7222-11'
OUTPUT = REF / 't3-page4-booster-turn-screen.json'
PRIOR = visible.OUTPUT
FACTORS = (.25, .5, 1, 2, 4)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def checked_prior():
    prior = json.loads(PRIOR.read_text())
    if prior['format'] != 'dac-monitor-t3-page4-visible-stage-screen-v1':
        raise ValueError('corrected 20-port predecessor changed')
    for name, digest in prior['input_sha256'].items():
        if sha(ROOT / name) != digest:
            raise ValueError(f'corrected 20-port predecessor stale: {name}')
    baseline = next(row for row in prior['cases']
                    if row['relative_polarity'] == {
                        'drive': 1, 'auxiliary': 1,
                        'high_voltage': 1, 'lower_taps': 1})
    if baseline['status'] != 'complete':
        raise ValueError('positive-sign corrected baseline did not solve')
    return prior, baseline


def run(ngspice, source_pdf):
    prior, baseline = checked_prior()
    if sha(ngspice) != prior['ngspice_sha256']:
        raise ValueError('ngspice differs from corrected baseline')
    checked = wrapper.run(source_pdf)
    if checked != json.loads(wrapper.OUTPUT.read_text()) or not checked['passed']:
        raise ValueError('source-visible KiCad interface changed')
    graph = json.loads(visible.GRAPH.read_text())
    parameters = visible.transferred_parameters(
        json.loads(visible.BASE_PARAMETERS.read_text()))
    transcription, parts, l3_r, l3_l = visible.prepared_parts(
        graph, checked['exported_nodes'])
    drive = next(group for group in graph['groups'] if group['id'] == 'drive')
    if drive['taps'] != ['X2_7', 'X2_13', 'X2_11', 'X2_12', 'X2_10', 'X2_4']:
        raise ValueError('source-visible booster tap order changed')
    sections = parameters['groups']['drive']
    varied = list(range(drive['taps'].index('X2_13'),
                        drive['taps'].index('X2_10')))
    if varied != [1, 2, 3] or any(sections[i]['turns']['value'] != 7 for i in varied):
        raise ValueError('provisional booster section values changed')
    candidate = next(row for row in tc.enumerate_candidates(graph)
                     if row['polarity'] == baseline['relative_polarity'])
    catalog = json.loads(boost.rail.CATALOG.read_text())
    yoke_row = next(row for row in catalog['class_cases'] if row['type'] == 'TBY7')
    yoke = (yoke_row['line_inductance_h'], yoke_row['line_resistance_ohm'])
    bounds = prior['targets']
    cases = []
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / 'page4-visible-transcription.json'
        path.write_text(json.dumps(transcription, indent=2) + '\n')
        saved = stage.TRANSCRIPTION
        try:
            stage.TRANSCRIPTION = path
            for factor in FACTORS:
                selected = copy.deepcopy(parameters)
                for i in varied:
                    turn = selected['groups']['drive'][i]['turns']
                    value = 7 * factor
                    if not turn['minimum'] <= value <= turn['maximum']:
                        raise ValueError('booster tap screen exceeds registered assumed bound')
                    turn['value'] = value
                    turn['rationale'] = (
                        f'Common {factor:g}x engineering scale of the three '
                        'X2:13-to-X2:10 sections; no original .11 turn count.')
                print(f'screening booster factor {factor:g}', flush=True)
                try:
                    observed = boost.measure(
                        ngspice, (graph, selected, candidate, parts, l3_r, l3_l, {}),
                        visible.FEED_V, yoke,
                        initial_boost_node_v=visible.FEED_V + visible.INITIAL_C21_V,
                        stop_s=visible.STOP_S,
                        window_start_s=visible.WINDOW_START_S)
                except (ValueError, subprocess.TimeoutExpired) as error:
                    if isinstance(error, ValueError) and not str(error).startswith(
                            'conditional boost stage failed:'):
                        raise
                    detail = next((line.strip() for line in str(error).splitlines()
                                   if 'Timestep too small' in line),
                                  str(error).splitlines()[0])
                    cases.append({'factor': factor, 'section_turns': 7 * factor,
                                  'status': 'solver_aborted', 'reason': detail,
                                  'joint_sampled_match': False})
                    continue
                checks = {
                    'sampled_eht': bounds['eht_v'][0] <= observed['eht_at_collector_peak_v'] <= bounds['eht_v'][1],
                    'sampled_yoke_current': bounds['yoke_current_pp_a'][0] <= observed['yoke_current_pp_a'] <= bounds['yoke_current_pp_a'][1],
                    'sampled_c21': bounds['c21_differential_v'][0] <= observed['c21_voltage_at_collector_peak_v'] <= bounds['c21_differential_v'][1],
                }
                cases.append({'factor': factor, 'section_turns': 7 * factor,
                              'status': 'complete', 'observed': observed,
                              'checks': checks,
                              'joint_sampled_match': all(checks.values())})
        finally:
            stage.TRANSCRIPTION = saved
    nominal = next(row for row in cases if row['factor'] == 1)
    if nominal['status'] != 'complete':
        raise ValueError('nominal corrected booster case did not solve')
    for key, tolerance in (('eht_at_collector_peak_v', .02),
                           ('yoke_current_pp_a', 2e-6),
                           ('c21_voltage_at_collector_peak_v', .002)):
        if abs(nominal['observed'][key] - baseline['observed'][key]) > tolerance:
            raise ValueError(f'corrected booster baseline differs: {key}')
    dependencies = (PRIOR, visible.GRAPH, visible.BASE_PARAMETERS,
                    wrapper.OUTPUT, wrapper.CANDIDATE_SHEET,
                    stage.TRANSCRIPTION, stage.MODELS, stage.PROFILE,
                    boost.rail.CATALOG, boost.bridge.MODEL,
                    ROOT / 'magnetics.py', ROOT / 'transformer_candidates.py',
                    ROOT / 'page4_t3_visible_wrapper.py',
                    ROOT / 't3_page4_visible_stage_screen.py',
                    ROOT / 't3_brimar_boost_boundary_screen.py',
                    ROOT / 't3_output_stage_sweep.py', Path(__file__))
    return {
        'format': 'dac-monitor-t3-page4-booster-turn-screen-v1',
        'qualification': 'five 20 ms common-scale source-visible booster section sensitivities within assumed, not documented, turns bounds; one positive-polarity 20-port graph and prescribed drive, no installed T3 or periodic qualification',
        'input_sha256': {str(path.relative_to(ROOT)): sha(path) for path in dependencies},
        'source_pdf_sha256': sha(source_pdf),
        'ngspice_sha256': sha(ngspice),
        'varied_sections': [list(pair) for pair in zip(drive['taps'][1:4],
                                                       drive['taps'][2:5])],
        'factors': list(FACTORS),
        'fixed_conditions': prior['conditions'],
        'targets': bounds,
        'cases': cases,
        'complete_count': sum(row['status'] == 'complete' for row in cases),
        'solver_aborted_count': sum(row['status'] == 'solver_aborted' for row in cases),
        'joint_sampled_match_count': sum(row['joint_sampled_match'] for row in cases),
        'interpretation': (
            'Only the three hypothetical X2:13-to-X2:10 sections change. '
            'Their 1.75–28-turn interval is an assumed bound, not a .11 '
            'measurement; sampled success would not qualify a physical '
            'booster ratio or settled periodic state.'),
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ngspice', type=Path, required=True)
    parser.add_argument('--source-pdf', type=Path, default=visible.SOURCE_PDF)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args()
    report = run(args.ngspice, args.source_pdf)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    for row in report['cases']:
        if row['status'] == 'solver_aborted':
            print(row['factor'], row['status'], row['reason'])
        else:
            values = row['observed']
            print(row['factor'], values['eht_at_collector_peak_v'],
                  values['yoke_current_pp_a'],
                  values['c21_voltage_at_collector_peak_v'],
                  row['joint_sampled_match'])
