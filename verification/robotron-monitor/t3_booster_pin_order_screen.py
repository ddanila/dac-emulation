"""Compare source-corrected booster pins under two conditional T3 tap orders."""

import copy
import hashlib
import json
from pathlib import Path
import tempfile

import t3_brimar_boost_boundary_screen as boost
import transformer_candidates


ROOT = Path(__file__).resolve().parent
REF = ROOT / 'reference/k7222-11'
OUTPUT = REF / 't3-booster-pin-order-screen.json'
SOURCE_COMPARISON = REF / 'page4-booster-comparison.json'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def source_order_inputs(inputs, transcription):
    graph = copy.deepcopy(inputs[0])
    drive = next(group for group in graph['groups'] if group['id'] == 'drive')
    if drive['taps'] != ['X2_7', 'X2_10', 'X2_11', 'X2_12', 'X2_13', 'X2_4']:
        raise ValueError('legacy drive order changed')
    drive['taps'] = ['X2_7', 'X2_13', 'X2_11', 'X2_12', 'X2_10', 'X2_4']
    drive['assumption'] = ('Candidate section order follows visible page-4 terminal '
                           'positions; internal winding continuity is still unverified.')
    candidate = next(row for row in transformer_candidates.enumerate_candidates(graph)
                     if row['polarity'] == inputs[2]['polarity'])
    ports = [port for group in graph['groups'] for port in group['taps']]
    selected = copy.deepcopy(inputs[3])
    t3 = next(part for part in selected if part['source_id'] == '012-6921:T3')
    node_by_port = dict(zip(transcription['ports'], t3['nodes']))
    t3['nodes'] = [node_by_port[port] for port in ports]
    reordered_transcription = copy.deepcopy(transcription)
    reordered_transcription['ports'] = ports
    return (graph, inputs[1], candidate, selected, *inputs[4:]), reordered_transcription


def run(ngspice):
    source = json.loads(SOURCE_COMPARISON.read_text())
    if not source['passed'] or not all(source['checks'].values()):
        raise ValueError('page-4 booster pin comparison is not passing')
    inputs = boost.pulse.setup()
    transcription = json.loads(boost.stage.TRANSCRIPTION.read_text())
    selected = next(part for part in inputs[3] if part['source_id'] == '012-6921:T3')
    nodes = dict(zip(transcription['ports'], selected['nodes']))
    if nodes['X2_13'] != 'h_boosttap' or nodes['X2_10'] != 'h_boost':
        raise ValueError('source-corrected external booster wiring changed')
    catalog = json.loads(boost.rail.CATALOG.read_text())
    tby7 = next(row for row in catalog['class_cases'] if row['type'] == 'TBY7')
    yoke = (tby7['line_inductance_h'], tby7['line_resistance_ohm'])
    feed = 42.504
    initial = feed + 65
    old = copy.deepcopy(inputs[3])
    old_t3 = next(part for part in old if part['source_id'] == '012-6921:T3')
    a, b = transcription['ports'].index('X2_10'), transcription['ports'].index('X2_13')
    old_t3['nodes'][a], old_t3['nodes'][b] = old_t3['nodes'][b], old_t3['nodes'][a]
    prior_inputs = (*inputs[:3], old, *inputs[4:])
    source_inputs, alternate_transcription = source_order_inputs(inputs, transcription)
    results = {}
    results['pre_correction_external_pins'] = boost.measure(
        ngspice, prior_inputs, feed, yoke, initial_boost_node_v=initial)
    results['corrected_pins_legacy_sections'] = boost.measure(
        ngspice, inputs, feed, yoke, initial_boost_node_v=initial)
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / 'source-order-transcription.json'
        path.write_text(json.dumps(alternate_transcription))
        saved = boost.stage.TRANSCRIPTION
        try:
            boost.stage.TRANSCRIPTION = path
            results['corrected_pins_source_order_sections'] = boost.measure(
                ngspice, source_inputs, feed, yoke, initial_boost_node_v=initial)
        finally:
            boost.stage.TRANSCRIPTION = saved
    files = (SOURCE_COMPARISON, boost.stage.GRAPH, boost.stage.PARAMETERS,
             boost.stage.TRANSCRIPTION, boost.stage.MODELS, boost.rail.CATALOG,
             ROOT / 't3_brimar_boost_boundary_screen.py', Path(__file__))
    return {
        'format': 'dac-monitor-t3-booster-pin-order-screen-v1',
        'qualification': 'three prescribed-drive 5 ms TBY7 cases; source-corrected external pins, but no internal winding or periodic operating-point qualification',
        'input_sha256': {str(path.relative_to(ROOT)): sha(path) for path in files},
        'ngspice_sha256': sha(ngspice),
        'conditions': {'feed_v': feed, 'initial_c21_differential_v': 65,
                       'upper_return_tied': True, 'cold_mode': 'hv_only_grounded',
                       'centering_link_pair': 'E1+E2', 'yoke_type': 'TBY7',
                       'sample_window_s': [0.004, 0.005]},
        'drive_tap_orders': {'legacy': next(group['taps'] for group in inputs[0]['groups']
                                            if group['id'] == 'drive'),
                             'source_order': next(group['taps'] for group in source_inputs[0]['groups']
                                                  if group['id'] == 'drive')},
        'candidate_polarity': inputs[2]['polarity'],
        'cases': results,
        'interpretation': ('The source-corrected external pin assignment alone changes '
                           'this conditional stage strongly under the legacy section '
                           'order. Reordering the hypothetical internal sections to '
                           'match the visible tap positions restores the pre-correction '
                           'electrical result. That is an isomorphic conditional model, '
                           'not evidence of actual T3 internal continuity or settled boost.'),
    }


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ngspice', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args()
    report = run(args.ngspice)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    for name, row in report['cases'].items():
        print(name, row['eht_at_collector_peak_v'], row['c21_voltage_at_collector_peak_v'])
