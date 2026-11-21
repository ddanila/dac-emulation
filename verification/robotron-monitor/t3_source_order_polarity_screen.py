"""Screen source-order T3 sign candidates against isolated diode function and C21."""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

import t3_booster_pin_order_screen as order
import t3_flyback_sign as hv
import t3_g1_polarity_filter as g1
import t3_brimar_boost_boundary_screen as boost
import transformer_candidates as candidates


ROOT = Path(__file__).resolve().parent
REF = ROOT / 'reference/k7222-11'
OUTPUT = REF / 't3-source-order-polarity-screen.json'
YOKE_BOUNDARY = REF / 'a5-yoke-class-boundary.json'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(ngspice):
    resolved = shutil.which('ngspice')
    if resolved is None or sha(resolved) != sha(ngspice):
        raise ValueError('isolated sign checks need the same ngspice binary')
    source = json.loads(order.SOURCE_COMPARISON.read_text())
    if not source['passed'] or not all(source['checks'].values()):
        raise ValueError('page-4 external booster wiring is not source-checked')
    initial = boost.pulse.setup()
    transcription = json.loads(boost.stage.TRANSCRIPTION.read_text())
    selected_t3 = next(part for part in initial[3]
                       if part['source_id'] == '012-6921:T3')
    nodes = dict(zip(transcription['ports'], selected_t3['nodes']))
    if nodes['X2_13'] != 'h_boosttap' or nodes['X2_10'] != 'h_boost':
        raise ValueError('source-corrected external booster wiring changed')
    inputs, alternate_transcription = order.source_order_inputs(initial, transcription)
    graph, parameters = inputs[:2]
    boundary = json.loads(YOKE_BOUNDARY.read_text())
    current_bounds = boundary['axes']['horizontal']['current_pp_a']['bounds']
    eht_bounds = boundary['target']['eht_v']
    c21_bounds = [60, 70]
    catalog = json.loads(boost.rail.CATALOG.read_text())
    yoke_row = next(row for row in catalog['class_cases'] if row['type'] == 'TBY7')
    yoke = (yoke_row['line_inductance_h'], yoke_row['line_resistance_ohm'])
    feed = 42.504
    signed = []
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        for candidate in candidates.enumerate_candidates(graph):
            pulses = {}
            for backend in ('flux', 'xspice'):
                pulses[backend] = {
                    'hv_v': hv.isolated_pulse(graph, candidate, parameters, backend,
                                              root / (candidate['id'] + '-hv-' + backend)),
                    'g1_v': g1.isolated_aux_pulse(graph, candidate, parameters, backend,
                                                  root / (candidate['id'] + '-g1-' + backend)),
                }
            sign_compatible = all(value['hv_v'] > .01 and value['g1_v'] < -.01
                                  for value in pulses.values())
            signed.append({'candidate_id': candidate['id'],
                           'polarity': candidate['polarity'],
                           'isolated_80ns': pulses,
                           'sign_compatible': sign_compatible})
        selected = [row for row in signed if row['sign_compatible']]
        if len(selected) != 4:
            raise ValueError(f'expected four functional sign candidates, got {len(selected)}')
        path = root / 'source-order-transcription.json'
        path.write_text(json.dumps(alternate_transcription))
        saved = boost.stage.TRANSCRIPTION
        try:
            boost.stage.TRANSCRIPTION = path
            for row in selected:
                candidate = next(item for item in candidates.enumerate_candidates(graph)
                                 if item['id'] == row['candidate_id'])
                case_inputs = (graph, parameters, candidate, *inputs[3:])
                measured = boost.measure(ngspice, case_inputs, feed, yoke,
                                         initial_boost_node_v=feed + 65,
                                         stop_s=.020, window_start_s=.019)
                row['stage_20ms'] = measured
                row['sampled_checks'] = {
                    'eht': eht_bounds[0] <= measured['eht_at_collector_peak_v'] <= eht_bounds[1],
                    'yoke_current': current_bounds[0] <= measured['yoke_current_pp_a'] <= current_bounds[1],
                    'c21': c21_bounds[0] <= measured['c21_voltage_at_collector_peak_v'] <= c21_bounds[1],
                }
                row['joint_sampled_match'] = all(row['sampled_checks'].values())
        finally:
            boost.stage.TRANSCRIPTION = saved
    dependencies = (order.SOURCE_COMPARISON, order.SOURCE_READ,
                    order.SOURCE_ORDER_VARIANT, boost.stage.GRAPH,
                    boost.stage.PARAMETERS, boost.stage.TRANSCRIPTION,
                    boost.stage.MODELS, boost.rail.CATALOG, YOKE_BOUNDARY,
                    ROOT / 't3_flyback_sign.py', ROOT / 't3_g1_polarity_filter.py',
                    ROOT / 't3_booster_pin_order_screen.py',
                    ROOT / 't3_brimar_boost_boundary_screen.py', Path(__file__))
    return {
        'format': 'dac-monitor-t3-source-order-polarity-screen-v1',
        'qualification': 'isolated HV/G1 sign filter plus 20 ms prescribed-drive TBY7 stage for a source-order X2 variant; no internal-continuity, periodic or installed-stage qualification',
        'input_sha256': {str(path.relative_to(ROOT)): sha(path) for path in dependencies},
        'ngspice_sha256': sha(ngspice),
        'conditions': {'feed_v': feed, 'initial_c21_differential_v': 65,
                       'window_s': [0.019, 0.020], 'upper_return_tied': True,
                       'cold_mode': 'hv_only_grounded', 'centering_link_pair': 'E1+E2',
                       'yoke_type': 'TBY7'},
        'targets': {'eht_v': eht_bounds, 'yoke_current_pp_a': current_bounds,
                    'c21_differential_v': c21_bounds},
        'candidates': signed,
        'sign_compatible_count': len(selected),
        'joint_sampled_match_count': sum(row['joint_sampled_match'] for row in selected),
        'interpretation': ('Both isolated diode functions prune the source-order variant '
                           'to four relative-polarity candidates. The 20 ms stage cases '
                           'remain conditional on the internal section order, transferred '
                           'turns, prescribed drive, return and yoke class; even a joint '
                           'sampled match would not prove a periodic operating point.'),
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ngspice', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args()
    result = run(args.ngspice)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(result['sign_compatible_count'], 'sign candidates,',
          result['joint_sampled_match_count'], 'joint sampled matches')
