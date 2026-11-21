"""Screen all relative polarities of the source-visible 20-port T3 candidate.

The transferred numbers are a deliberately conditional sensitivity set. A
passing sampled target is not a factory winding or settled monitor result.
"""

import argparse
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

import t3_brimar_boost_boundary_screen as boost
import t3_output_stage_sweep as stage
import t3_tp17_path_sweep as tp17
import transformer_candidates as tc
import page4_t3_visible_wrapper as wrapper


ROOT = Path(__file__).resolve().parent
REF = ROOT / 'reference/k7222-11'
GRAPH = REF / 't3-page4-visible-graph.json'
BASE_PARAMETERS = REF / 't3-coupled-source-ac-loss-parameters.json'
BOUNDARY = REF / 'a5-yoke-class-boundary.json'
OUTPUT = REF / 't3-page4-visible-stage-screen.json'
SOURCE_PDF = ROOT.parents[1] / 'build/monitor/phase-a/sources/older.pdf'
STOP_S = .020
WINDOW_START_S = .019
FEED_V = 42.504
INITIAL_C21_V = 65.0


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def transferred_parameters(base):
    """Place prior provisional sections on the new labels, without fitting."""
    parameters = copy.deepcopy(base)
    groups = parameters['groups']
    if (list(groups) != ['drive', 'auxiliary', 'high_voltage', 'upper_taps',
                         'lower_taps'] or
            [len(groups[name]) for name in groups] != [5, 2, 1, 2, 4] or
            groups['high_voltage'][0]['turns']['value'] != 1768 or
            [section['turns']['value'] for section in groups['upper_taps']] != [3, 30] or
            parameters['high_voltage_coupling']['value'] != .92):
        raise ValueError('provisional source sections changed; re-evaluate transfer')
    upper = groups.pop('upper_taps')
    hv = groups['high_voltage'][0]
    bridges = []
    for labels in (('X1:1', 'X1:2'), ('X1:2', 'X1:3')):
        section = copy.deepcopy(upper[0])
        section['turns']['value'] = 1
        section['turns']['rationale'] = (
            f'One-turn engineering bridge {labels[0]}–{labels[1]} for this '
            'sensitivity screen; no .11 winding evidence.')
        bridges.append(section)
    groups['high_voltage'] = [hv, *bridges, *upper]
    parameters['rationale'] = (
        'Conditional page-4-visible T3 screen: transfer old cross-revision '
        'overwind and provisional tap sections to the corrected graph, with '
        'two assumed one-turn bridges. No installed .11 winding is identified.')
    parameters['source_basis']['page4_visible_transfer'] = (
        'The old 1768-turn HV section is assigned to X3:1–X1:1, one-turn '
        'bridges to X1:1–X1:2 and X1:2–X1:3, and the old 3/30-turn upper '
        'sections to X1:3–X1:5–X1:7. Source labels support only the port '
        'inventory and external links, not these turns or continuity.')
    return parameters


def prepared_parts(graph, exported_nodes):
    transcription, parts, l3_r, l3_l = stage.source_parts()
    by_id = {part['source_id']: part for part in transcription['components']}
    parts += [by_id['012-6921:' + name] for name in tp17.SOURCE_PARTS]
    ports = [pin for group in graph['groups'] for pin in group['taps']]
    if set(ports) != set(exported_nodes) or len(ports) != 20:
        raise ValueError('20-port source-visible export differs from graph')
    t3 = next(part for part in parts if part['source_id'] == '012-6921:T3')
    t3['nodes'] = [exported_nodes[port] for port in ports]
    transcription['ports'] = ports
    transcription['port_nets'] = exported_nodes
    next(part for part in transcription['components']
         if part['source_id'] == '012-6921:T3')['nodes'] = t3['nodes']
    transcription['qualification'] = (
        'page-4-visible 20-port external-interface candidate; numerical '
        'winding parameters are independent hypotheses')
    obsolete = [note for note in transcription['assumptions']
                if note.startswith('Manual p19 fixes HV winding terminals X1:1/16;')]
    if len(obsolete) != 1:
        raise ValueError('historical HV terminal assumption changed')
    transcription['assumptions'] = [note for note in transcription['assumptions']
                                    if note not in obsolete]
    transcription['assumptions'].append(
        'Page 4 shows V21 pads X3:1/X3:2 and the X1:2–X2:3 conductor; '
        'manual connection 16 has no qualified connector-prefix mapping. '
        'Internal sections and return remain hypothetical.')
    return transcription, parts, l3_r, l3_l


def run(ngspice, source_pdf):
    checked = wrapper.run(source_pdf)
    if checked != json.loads(wrapper.OUTPUT.read_text()) or not checked['passed']:
        raise ValueError('20-port KiCad source comparison is stale')
    graph = json.loads(GRAPH.read_text())
    parameters = transferred_parameters(json.loads(BASE_PARAMETERS.read_text()))
    transcription, parts, l3_r, l3_l = prepared_parts(
        graph, checked['exported_nodes'])
    boundary = json.loads(BOUNDARY.read_text())
    eht_bounds = boundary['target']['eht_v']
    current_bounds = boundary['axes']['horizontal']['current_pp_a']['bounds']
    c21_bounds = [60, 70]
    catalog = json.loads(boost.rail.CATALOG.read_text())
    yoke_row = next(row for row in catalog['class_cases'] if row['type'] == 'TBY7')
    yoke = (yoke_row['line_inductance_h'], yoke_row['line_resistance_ohm'])
    cases = []
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / 'page4-visible-transcription.json'
        path.write_text(json.dumps(transcription, indent=2) + '\n')
        saved = stage.TRANSCRIPTION
        try:
            stage.TRANSCRIPTION = path
            for candidate in tc.enumerate_candidates(graph):
                print(f"screening {candidate['id']} {candidate['polarity']}", flush=True)
                try:
                    observed = boost.measure(
                        ngspice, (graph, parameters, candidate, parts, l3_r, l3_l, {}),
                        FEED_V, yoke, initial_boost_node_v=FEED_V + INITIAL_C21_V,
                        stop_s=STOP_S, window_start_s=WINDOW_START_S)
                except (ValueError, subprocess.TimeoutExpired) as error:
                    if isinstance(error, ValueError) and not str(error).startswith(
                            'conditional boost stage failed:'):
                        raise
                    detail = next((line.strip() for line in str(error).splitlines()
                                   if 'Timestep too small' in line),
                                  str(error).splitlines()[0])
                    cases.append({'candidate_id': candidate['id'],
                                  'relative_polarity': candidate['polarity'],
                                  'status': 'solver_aborted', 'reason': detail,
                                  'joint_sampled_match': False})
                    continue
                checks = {
                    'sampled_eht': eht_bounds[0] <= observed['eht_at_collector_peak_v'] <= eht_bounds[1],
                    'sampled_yoke_current': current_bounds[0] <= observed['yoke_current_pp_a'] <= current_bounds[1],
                    'sampled_c21': c21_bounds[0] <= observed['c21_voltage_at_collector_peak_v'] <= c21_bounds[1],
                }
                cases.append({'candidate_id': candidate['id'],
                              'relative_polarity': candidate['polarity'],
                              'status': 'complete', 'observed': observed,
                              'checks': checks,
                              'joint_sampled_match': all(checks.values())})
        finally:
            stage.TRANSCRIPTION = saved
    dependencies = (GRAPH, BASE_PARAMETERS, BOUNDARY, wrapper.OUTPUT,
                    wrapper.CANDIDATE_SHEET, wrapper.SOURCE,
                    stage.TRANSCRIPTION, stage.MODELS, stage.PROFILE,
                    boost.rail.CATALOG, boost.bridge.MODEL,
                    ROOT / 'magnetics.py', ROOT / 'transformer_candidates.py',
                    ROOT / 'page4_t3_visible_wrapper.py',
                    ROOT / 'centering_bridge_check.py',
                    ROOT / 'steady_supply.py',
                    ROOT / 't3_centering_return_screen.py',
                    ROOT / 't3_brimar_boost_boundary_screen.py',
                    ROOT / 't3_stage_refinement_screen.py',
                    ROOT / 't3_tp17_path_sweep.py',
                    ROOT / 't3_output_stage_sweep.py', Path(__file__))
    return {
        'format': 'dac-monitor-t3-page4-visible-stage-screen-v1',
        'qualification': 'eight 20 ms prescribed-drive polarity sensitivities on a source-visible external T3 interface with transferred provisional turns and one TBY7 class yoke; no installed winding, drive or periodic-state qualification',
        'input_sha256': {str(path.relative_to(ROOT)): sha(path) for path in dependencies},
        'source_pdf_sha256': sha(source_pdf),
        'ngspice_sha256': sha(ngspice),
        'parameter_transfer': parameters,
        'ports_in_magnetic_order': transcription['ports'],
        'external_nodes': checked['exported_nodes'],
        'conditions': {'feed_v': FEED_V, 'initial_c21_differential_v': INITIAL_C21_V,
                       'window_s': [WINDOW_START_S, STOP_S],
                       'yoke_class': 'TBY7', 'centering_link_pair': 'E1+E2',
                       'maximum_step_ns': 50},
        'targets': {'eht_v': eht_bounds, 'yoke_current_pp_a': current_bounds,
                    'c21_differential_v': c21_bounds},
        'cases': cases,
        'complete_count': sum(row['status'] == 'complete' for row in cases),
        'solver_aborted_count': sum(row['status'] == 'solver_aborted' for row in cases),
        'joint_sampled_match_count': sum(row['joint_sampled_match'] for row in cases),
        'interpretation': (
            'This tests the corrected external port identities and one explicit '
            'provisional section transfer across all relative polarities. A '
            'sampled match would not select installed turns, return or periodic '
            'state; a solver abort remains unscored. Misses do not reject all '
            'possible 20-port winding graphs.'),
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ngspice', type=Path, required=True)
    parser.add_argument('--source-pdf', type=Path, default=SOURCE_PDF)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args()
    report = run(args.ngspice, args.source_pdf)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    for row in report['cases']:
        if row['status'] == 'solver_aborted':
            print(row['relative_polarity'], row['status'], row['reason'])
        else:
            values = row['observed']
            print(row['relative_polarity'],
                  round(values['eht_at_collector_peak_v'], 2),
                  round(values['yoke_current_pp_a'], 5),
                  round(values['c21_voltage_at_collector_peak_v'], 3),
                  row['joint_sampled_match'])
