"""Prescribed-drive horizontal output/T3/yoke sensitivity, not monitor acceptance."""
import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import statistics
import subprocess
import tempfile

import transformer_candidates

ROOT = Path(__file__).resolve().parent
GRAPH = ROOT/'reference/k7222-11/t3-winding-hypothesis.json'
PARAMETERS = ROOT/'reference/k7222-11/t3-initial-parameters.json'
AC_LOSS = ROOT/'reference/k7222-11/t3-ac-loss-parameters.json'
TRANSCRIPTION = ROOT/'reference/k7222-11/horizontal-output-transcription.json'
PROFILE = ROOT/'profiles/k7222-11-horizontal-oscillator.json'
MODELS = ROOT/'circuits/k7222-11-horizontal-models.cir'
SIGN = ROOT/'reference/k7222-11/t3-flyback-sign-filter.json'
OPERATING = ROOT/'reference/k7222-11/t3-collector-eht-comparator.json'
WINDING = ROOT/'reference/k7222-11/t3-hv-winding-comparator.json'
DESIGN = ROOT/'reference/k7222-11/design-point.json'
PARTS = ('C21', 'C22', 'C25', 'C26', 'C27', 'C30', 'C31', 'C32',
         'R35', 'R36', 'L3', 'V16', 'V17', 'V18', 'V21', 'T3')
TURNS = (1000, 1768, 2035, 2409)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_parts():
    transcription = json.loads(TRANSCRIPTION.read_text())
    by_id = {part['source_id']: part for part in transcription['components']}
    wanted = [f'012-6921:{name}' for name in PARTS]
    if any(key not in by_id for key in wanted):
        raise ValueError('horizontal output source part missing')
    t3 = by_id['012-6921:T3']
    if t3['value'] != 'T3_CANDIDATE' or len(t3['nodes']) != len(transcription['ports']):
        raise ValueError('T3 wrapper differs from live source transcription')
    profile = json.loads(PROFILE.read_text())['parameters']
    l3_r = profile['horizontal_linearity_r']['nominal']
    l3_l = profile['horizontal_linearity_l']['nominal']
    if l3_r != .1 or l3_l != 20e-6:
        raise ValueError('L3 nominal changed; review stage bench')
    return transcription, [by_id[key] for key in wanted], l3_r, l3_l


def deck(graph, parameters, candidate, parts, l3_r, l3_l, trace, *, tube_c_f=1e-9):
    magnetic, metadata = transformer_candidates.compile_model(graph, candidate,
                                                                parameters, backend='flux')
    t3 = next(part for part in parts if part['source_id'] == '012-6921:T3')
    if metadata['ports'] != json.loads(TRANSCRIPTION.read_text())['ports']:
        raise ValueError('compiled T3 ports differ from stage wiring')
    lines = ['Prescribed-drive source-addressed output stage; not a connected monitor',
             magnetic, MODELS.read_text(),
             f'.param horizontal_linearity_r={l3_r:.15g}',
             f'.param horizontal_linearity_l={l3_l:.15g}']
    lines += [' '.join([part['reference'], *part['nodes'], part['value']]) for part in parts]
    nodes = sorted({node for node in t3['nodes'] if node not in ('0', 'h_hot', 'h_feed')})
    lines += [f'Rauxref{i} {node} 0 1G' for i, node in enumerate(nodes)]
    lines += [
        'Vfeed h_feed 0 41',
        'Vbase drive 0 PULSE(-2.7 1.3 1u 20n 20n 46.5u 62.5u)',
        'Rbase drive h_outbase 1',
        'Rfeedback h_feedback 0 1Meg', 'Rsync h_sync 0 1Meg',
        'Rhorizontal hy1 h_winding 2', 'Lhorizontal h_winding hy2 4m',
        'Rhy2ref hy2 0 1G',
        f'Ctube eht 0 {tube_c_f:.15g}', 'Rhv eht 0 200Meg',
        '.ic v(h_boost)=65',
        '.options reltol=.001 abstol=1e-9 method=gear',
        '.control', 'set wr_singlescale', 'set wr_vecnames',
        'tran 100n 5m 4m',
        f'wrdata {trace} v(h_hot) v(eht) v(h_feedback) v(h_sync) i(Lhorizontal) v(h_boost)',
        'quit', '.endc', '.end',
    ]
    return '\n'.join(lines) + '\n'


def summarize(trace, expected_end_s=.005):
    with trace.open() as stream:
        columns = next(stream).split()
        expected = ['time', 'v(h_hot)', 'v(eht)', 'v(h_feedback)',
                    'v(h_sync)', 'i(Lhorizontal)', 'v(h_boost)']
        driver_columns = ['v(h_outbase)', 'v(h_drivecol)']
        if columns[:len(expected)] != expected or columns[len(expected):] not in ([], driver_columns):
            raise ValueError('unexpected output-stage trace columns')
        rows = [list(map(float, line.split())) for line in stream if line.strip()]
    if len(rows) < 1000 or abs(rows[-1][0] - expected_end_s) > 1e-9:
        raise ValueError(f'output-stage solve did not reach {expected_end_s:g} s')
    if any(len(row) != len(columns) or not all(math.isfinite(v) for v in row)
           for row in rows):
        raise ValueError('incomplete or nonfinite output-stage samples')
    hot = [row[1] for row in rows]
    threshold = min(hot) + .1*(max(hot)-min(hot))
    edges = []
    for a, b in zip(rows, rows[1:]):
        if (a[1]-threshold)*(b[1]-threshold) < 0:
            instant = a[0] + (threshold-a[1])*(b[0]-a[0])/(b[1]-a[1])
            edges.append((instant, 'rise' if b[1] > a[1] else 'fall'))
    widths = [(b[0]-a[0])*1e6 for a, b in zip(edges, edges[1:])
              if a[1] == 'rise' and b[1] == 'fall']
    if not widths:
        raise ValueError('no collector flyback pulse')
    eht = [row[2] for row in rows]
    result = {
        'sample_count': len(rows), 'sample_window_s': [rows[0][0], rows[-1][0]],
        'collector_peak_v': max(hot), 'collector_min_v': min(hot),
        'eht_peak_v': max(eht), 'eht_final_v': eht[-1],
        'eht_same_phase_drift_v_over_16_lines': eht[-1]-eht[0],
        'feedback_swing_v': max(row[3] for row in rows)-min(row[3] for row in rows),
        'sync_swing_v': max(row[4] for row in rows)-min(row[4] for row in rows),
        'yoke_current_range_a': [min(row[5] for row in rows), max(row[5] for row in rows)],
        'boost_range_v': [min(row[6] for row in rows), max(row[6] for row in rows)],
        'flyback_pulse_count': len(widths),
        'flyback_width_us_at_10pct_swing_median': statistics.median(widths),
    }
    if columns[len(expected):] == driver_columns:
        result['output_base_range_v'] = [min(row[7] for row in rows), max(row[7] for row in rows)]
        result['driver_collector_swing_v'] = max(row[8] for row in rows)-min(row[8] for row in rows)
    return result


def simulate(graph, parameters, candidate, parts, l3_r, l3_l, *, tube_c_f=1e-9):
    with tempfile.TemporaryDirectory() as directory:
        folder = Path(directory)
        trace = folder/'late.dat'
        circuit = folder/'stage.cir'
        circuit.write_text(deck(graph, parameters, candidate, parts, l3_r, l3_l,
                                trace, tube_c_f=tube_c_f))
        result = subprocess.run(['ngspice', '-b', str(circuit)],
                                capture_output=True, text=True)
        log = result.stdout + result.stderr
        aborted = (result.returncode != 0 or 'tran simulation(s) aborted' in log
                   or 'Timestep too small' in log or 'Error:' in log)
        if aborted or not trace.is_file():
            return {'status': 'aborted', 'timestep_failure': 'Timestep too small' in log}
        return {'status': 'complete', **summarize(trace)}


def run():
    graph = json.loads(GRAPH.read_text())
    active = json.loads(PARAMETERS.read_text())
    ac_loss = json.loads(AC_LOSS.read_text())
    transcription, parts, l3_r, l3_l = source_parts()
    sign = json.loads(SIGN.read_text())
    comparator = json.loads(OPERATING.read_text())
    documented_eht = json.loads(DESIGN.read_text())['high_voltage_ratio']['eht_target_v']
    documented_range = [documented_eht['minimum'], documented_eht['maximum']]
    accepted = set(sign['accepted_candidate_ids'])
    candidates = [item for item in transformer_candidates.enumerate_candidates(graph)
                  if item['id'] in accepted]
    if len(candidates) != 8:
        raise ValueError('expected eight sign-compatible T3 candidates')
    baseline = simulate(graph, active, candidates[0], parts, l3_r, l3_l)
    rows = []
    for candidate in candidates:
        for turns in TURNS:
            modified = copy.deepcopy(ac_loss)
            modified['groups']['high_voltage'][0]['turns']['value'] = turns
            result = simulate(graph, modified, candidate, parts, l3_r, l3_l)
            rows.append({'candidate_id': candidate['id'], 'polarity': candidate['polarity'],
                         'high_voltage_turns': turns, 'result': result})
    complete = [row for row in rows if row['result']['status'] == 'complete']
    collector_range = comparator['source']['reported_k7222_collector_pulse_v']
    eht_range = [v*1000 for v in comparator['source']['reported_k7222_eht_kv']]
    for row in complete:
        result = row['result']
        row['cross_revision_comparator_checks'] = {
            'collector_peak_in_reported_range': collector_range[0] <= result['collector_peak_v'] <= collector_range[1],
            'eht_final_in_reported_range': eht_range[0] <= result['eht_final_v'] <= eht_range[1],
            'eht_final_in_documented_range': documented_range[0] <= result['eht_final_v'] <= documented_range[1],
            'flyback_width_within_20pct_of_manual_16us': 12.8 <= result['flyback_width_us_at_10pct_swing_median'] <= 19.2,
        }
    representative = candidates[0]
    nominal_load = next(row['result'] for row in rows
                        if row['candidate_id'] == representative['id']
                        and row['high_voltage_turns'] == 1768)
    modified = copy.deepcopy(ac_loss)
    modified['groups']['high_voltage'][0]['turns']['value'] = 1768
    cap_cases = [
        {'tube_capacitance_f': cap, 'result': (nominal_load if cap == 1e-9 else
            simulate(graph, modified, representative, parts, l3_r, l3_l, tube_c_f=cap))}
        for cap in (.25e-9, 1e-9, 4e-9)]
    per_turn_complete = all(any(row['high_voltage_turns'] == turns for row in complete)
                            for turns in TURNS)
    return {
        'format': 'dac-monitor-t3-output-stage-sweep-v1',
        'qualification': 'prescribed-base-drive, ideal-feed, source-addressed output-stage sensitivity; not source-validated whole page, periodic monitor, A3 score or A5 winding freeze',
        'source_hashes': {path.name: sha(path) for path in
            (GRAPH, PARAMETERS, AC_LOSS, TRANSCRIPTION, PROFILE, MODELS, SIGN, OPERATING, WINDING, DESIGN)},
        'source_parts': [part['source_id'] for part in parts],
        'circuit_assumptions': [
            'Horizontal-output KiCad transcription supplies selected T3, V18, V16, V17, V21, L3, R35/R36 and capacitor branches; full page-4 source comparison is open.',
            'Ideal 41 V feed replaces source R42/L1/converter behavior, and a 1.3/-2.7 V, 46.5 us/16 us pulse through 1 ohm replaces T2/L4 and sync loop.',
            'Horizontal yoke is an exploratory 4 mH/2 ohm series branch; EHT load is 1 nF/200 Mohm without tube beam current.',
            'One-gigohm DC shunts and 1 Mohm feedback/sync loads stand in for omitted connections; the T3 X1:3/X2:3 tie and floating X1:16/X1:7 node remain the active unverified graph.',
            'Boost starts at an assumed 65 V; the trace is observed only from 4 to 5 ms, not proved periodic.',
            'Optional passive AC winding loss is an assumed-bound solver/impedance hypothesis, not a fitted transformer.',
        ],
        'reported_collector_range_v': collector_range,
        'reported_eht_range_v': eht_range,
        'documented_eht_range_v': documented_range,
        'manual_retrace_us': 16,
        'active_no_ac_loss_baseline': baseline,
        'candidate_results': rows,
        'tube_capacitance_sensitivity': {
            'candidate_id': representative['id'], 'high_voltage_turns': 1768,
            'qualification': 'isolated EHT-load capacitance endpoints from the assembly bounds; other stage assumptions fixed',
            'cases': cap_cases},
        'completed_cases': len(complete),
        'aborted_cases': len(rows)-len(complete),
        'joint_collector_eht_comparator_matches': [
            {'candidate_id': row['candidate_id'], 'high_voltage_turns': row['high_voltage_turns']}
            for row in complete if row['cross_revision_comparator_checks']['collector_peak_in_reported_range']
            and row['cross_revision_comparator_checks']['eht_final_in_reported_range']],
        'documented_eht_matches': [
            {'candidate_id': row['candidate_id'], 'high_voltage_turns': row['high_voltage_turns']}
            for row in complete if row['cross_revision_comparator_checks']['eht_final_in_documented_range']],
        'status': 'complete' if len(complete) == len(rows) else 'partial',
        'analysis_valid': per_turn_complete and all(case['result']['status'] == 'complete' for case in cap_cases),
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = run()
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(f"{report['completed_cases']}/{len(report['candidate_results'])} AC-loss cases complete; joint matches={len(report['joint_collector_eht_comparator_matches'])}; status={report['status']}")
    if not report['analysis_valid']:
        raise SystemExit(1)
