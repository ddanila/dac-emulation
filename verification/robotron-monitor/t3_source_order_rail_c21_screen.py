"""Screen source-order C21 against the documented 41P/R5 rail interval."""

import argparse
import hashlib
import json
from pathlib import Path
import tempfile

import t3_booster_pin_order_screen as order
import t3_brimar_boost_boundary_screen as boost
import t3_brimar_rail_boundary_screen as rail
import transformer_candidates


ROOT = Path(__file__).resolve().parent
REF = ROOT / 'reference/k7222-11'
OUTPUT = REF / 't3-source-order-rail-c21-screen.json'
SIGN_SCREEN = REF / 't3-source-order-polarity-screen.json'
BOUNDARY = REF / 'a5-yoke-class-boundary.json'
INVENTORY = REF / 'inventory.json'
SOURCE_PDF_SHA256 = '3c435063815af483a0fa98823a8a95a4178359e64f759344ee03cc0300e292dd'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(ngspice, source_pdf):
    if sha(source_pdf) != SOURCE_PDF_SHA256:
        raise ValueError('K7222.11 source PDF changed')
    source = json.loads(order.SOURCE_COMPARISON.read_text())
    if not source['passed'] or not all(source['checks'].values()):
        raise ValueError('page-4 booster wiring is not source-checked')
    inventory = {part['id']: part for part in json.loads(INVENTORY.read_text())['parts']}
    if any(inventory['012-6931:' + name]['value'] != value
           for name, value in (('R5', 1000), ('R6', 2400), ('R7', 30000))):
        raise ValueError('R5 feedback-divider source values changed')
    sign = json.loads(SIGN_SCREEN.read_text())
    for name, digest in sign['input_sha256'].items():
        if sha(ROOT / name) != digest:
            raise ValueError(f'source-order sign screen is stale: {name}')
    if sign['ngspice_sha256'] != sha(ngspice):
        raise ValueError('sign screen used a different ngspice')
    accepted = [row for row in sign['candidates'] if row['sign_compatible']]
    if len(accepted) != 4:
        raise ValueError('source-order sign candidate count changed')
    chosen = next(row for row in accepted
                  if row['polarity']['lower_taps'] == 1 and
                     row['polarity']['upper_taps'] == 1)
    initial = boost.pulse.setup()
    transcription = json.loads(boost.stage.TRANSCRIPTION.read_text())
    inputs, alternative = order.source_order_inputs(initial, transcription)
    candidate = next(row for row in transformer_candidates.enumerate_candidates(inputs[0])
                     if row['polarity'] == chosen['polarity'])
    inputs = (inputs[0], inputs[1], candidate, *inputs[3:])
    boundary = json.loads(BOUNDARY.read_text())
    eht = boundary['target']['eht_v']
    current = boundary['axes']['horizontal']['current_pp_a']['bounds']
    c21 = [60, 70]
    catalog = json.loads(boost.rail.CATALOG.read_text())
    tby7 = next(row for row in catalog['class_cases'] if row['type'] == 'TBY7')
    yoke = (tby7['line_inductance_h'], tby7['line_resistance_ohm'])
    cases = []
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / 'source-order-transcription.json'
        path.write_text(json.dumps(alternative))
        saved = boost.stage.TRANSCRIPTION
        try:
            boost.stage.TRANSCRIPTION = path
            for feed in (39., 41., 42.504, 43.):
                observed = boost.measure(ngspice, inputs, feed, yoke,
                                         initial_boost_node_v=feed + 65,
                                         stop_s=.020, window_start_s=.019)
                checks = {'eht': eht[0] <= observed['eht_at_collector_peak_v'] <= eht[1],
                          'yoke_current': current[0] <= observed['yoke_current_pp_a'] <= current[1],
                          'c21': c21[0] <= observed['c21_voltage_at_collector_peak_v'] <= c21[1]}
                cases.append({'feed_v': feed,
                              'r5_equivalent_position': rail.r5_position_for_feed(feed),
                              'initial_c21_differential_v': 65,
                              'observed': observed, 'sampled_checks': checks,
                              'joint_sampled_match': all(checks.values())})
        finally:
            boost.stage.TRANSCRIPTION = saved
    prior = chosen['stage_20ms']
    at_crossing = next(row for row in cases if row['feed_v'] == 42.504)['observed']
    for key, tolerance in (('eht_at_collector_peak_v', .02),
                           ('yoke_current_pp_a', 2e-6),
                           ('c21_voltage_at_collector_peak_v', .002)):
        if abs(at_crossing[key] - prior[key]) > tolerance:
            raise ValueError(f'42.504 V case differs from source-order sign screen: {key}')
    dependencies = (order.SOURCE_COMPARISON, order.SOURCE_READ,
                    order.SOURCE_ORDER_VARIANT, SIGN_SCREEN, BOUNDARY,
                    INVENTORY, boost.stage.GRAPH, boost.stage.PARAMETERS,
                    boost.stage.TRANSCRIPTION, boost.stage.MODELS,
                    boost.rail.CATALOG, ROOT / 'steady_supply.py',
                    ROOT / 't3_brimar_rail_boundary_screen.py',
                    ROOT / 't3_brimar_boost_boundary_screen.py',
                    ROOT / 't3_booster_pin_order_screen.py', Path(__file__))
    return {
        'format': 'dac-monitor-t3-source-order-rail-c21-screen-v1',
        'qualification': 'four 20 ms prescribed-drive TBY7 source-order cases over the 39–43 V 41P comparator interval; no installed R5 response, internal T3 continuity or periodic qualification',
        'source_pdf_sha256': SOURCE_PDF_SHA256,
        'input_sha256': {str(path.relative_to(ROOT)): sha(path) for path in dependencies},
        'ngspice_sha256': sha(ngspice),
        'candidate_id': candidate['id'],
        'candidate_polarity': candidate['polarity'],
        'fixed_conditions': {'upper_return_tied': True,
                             'cold_mode': 'hv_only_grounded',
                             'centering_link_pair': 'E1+E2',
                             'yoke_type': 'TBY7', 'window_s': [0.019, 0.020]},
        'targets': {'eht_v': eht, 'yoke_current_pp_a': current,
                    'c21_differential_v': c21},
        'cases': cases,
        'joint_sampled_match_count': sum(row['joint_sampled_match'] for row in cases),
        'interpretation': ('This rail-only screen checks whether R5-equivalent 41P '
                           'movement can explain the C21 gap under one source-order '
                           'sign and return hypothesis. It does not bound the actual '
                           'X2:4 drive pulse or qualify the installed monitor.'),
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ngspice', type=Path, required=True)
    parser.add_argument('--source-pdf', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args()
    report = run(args.ngspice, args.source_pdf)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    for row in report['cases']:
        measured = row['observed']
        print(row['feed_v'], measured['eht_at_collector_peak_v'],
              measured['yoke_current_pp_a'], measured['c21_voltage_at_collector_peak_v'])
