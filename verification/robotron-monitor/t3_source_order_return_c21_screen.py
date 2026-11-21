"""Check six source-order T3 return alternatives against C21 at 20 ms."""

import argparse
import copy
import hashlib
import json
from pathlib import Path
import tempfile

import t3_booster_pin_order_screen as order
import t3_brimar_boost_boundary_screen as boost
import transformer_candidates


ROOT = Path(__file__).resolve().parent
REF = ROOT / 'reference/k7222-11'
OUTPUT = REF / 't3-source-order-return-c21-screen.json'
SIGN = REF / 't3-source-order-polarity-screen.json'
RAIL = REF / 't3-source-order-rail-c21-screen.json'
BOUNDARY = REF / 'a5-yoke-class-boundary.json'
SOURCE_PDF_SHA256 = '3c435063815af483a0fa98823a8a95a4178359e64f759344ee03cc0300e292dd'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def selected_parts(parts, ports, joined, mode):
    if mode == 'shared_floating':
        selected = copy.deepcopy(parts)
        t3 = next(part for part in selected if part['source_id'] == '012-6921:T3')
        nodes = dict(zip(ports, t3['nodes']))
        if not joined:
            nodes['X1_3'] = 'h_upper_return'
        t3['nodes'] = [nodes[port] for port in ports]
        return selected
    selected, _ = boost.returns.variant_parts(parts, ports, joined, mode)
    return selected


def run(ngspice, source_pdf):
    if sha(source_pdf) != SOURCE_PDF_SHA256:
        raise ValueError('K7222.11 source PDF changed')
    comparison = json.loads(order.SOURCE_COMPARISON.read_text())
    if not comparison['passed'] or not all(comparison['checks'].values()):
        raise ValueError('external booster pins are not source-checked')
    rail = json.loads(RAIL.read_text())
    sign = json.loads(SIGN.read_text())
    for prior in (rail, sign):
        if prior['ngspice_sha256'] != sha(ngspice):
            raise ValueError('earlier source-order screen used a different ngspice')
        for name, digest in prior['input_sha256'].items():
            if sha(ROOT / name) != digest:
                raise ValueError(f'earlier source-order screen is stale: {name}')
    chosen = next(row for row in sign['candidates']
                  if row['sign_compatible'] and row['polarity']['lower_taps'] == 1
                  and row['polarity']['upper_taps'] == 1)
    inputs = boost.pulse.setup()
    transcription, base, _, _ = boost.stage.source_parts()
    by_id = {part['source_id']: part for part in transcription['components']}
    base += [by_id['012-6921:' + name] for name in boost.tp17.SOURCE_PARTS]
    boundary = json.loads(BOUNDARY.read_text())
    eht_bounds = boundary['target']['eht_v']
    current_bounds = boundary['axes']['horizontal']['current_pp_a']['bounds']
    c21_bounds = [60, 70]
    catalog = json.loads(boost.rail.CATALOG.read_text())
    tby7 = next(row for row in catalog['class_cases'] if row['type'] == 'TBY7')
    yoke = (tby7['line_inductance_h'], tby7['line_resistance_ohm'])
    feed = 42.504
    results = []
    with tempfile.TemporaryDirectory() as directory:
        alternate_path = Path(directory) / 'source-order-transcription.json'
        for joined in (True, False):
            for mode in ('shared_floating', 'hv_only_grounded', 'shared_grounded'):
                selected = selected_parts(base, transcription['ports'], joined, mode)
                current = (inputs[0], inputs[1], inputs[2], selected, *inputs[4:])
                alternate, alternate_transcription = order.source_order_inputs(
                    current, transcription)
                alternate_path.write_text(json.dumps(alternate_transcription))
                candidate = next(row for row in transformer_candidates.enumerate_candidates(alternate[0])
                                 if row['polarity'] == chosen['polarity'])
                alternate = (alternate[0], alternate[1], candidate, *alternate[3:])
                saved = boost.stage.TRANSCRIPTION
                try:
                    boost.stage.TRANSCRIPTION = alternate_path
                    observed = boost.measure(ngspice, alternate, feed, yoke,
                                             initial_boost_node_v=feed + 65,
                                             stop_s=.020, window_start_s=.019)
                finally:
                    boost.stage.TRANSCRIPTION = saved
                checks = {
                    'eht': eht_bounds[0] <= observed['eht_at_collector_peak_v'] <= eht_bounds[1],
                    'yoke_current': current_bounds[0] <= observed['yoke_current_pp_a'] <= current_bounds[1],
                    'c21': c21_bounds[0] <= observed['c21_voltage_at_collector_peak_v'] <= c21_bounds[1],
                }
                results.append({'upper_return_tied': joined, 'cold_mode': mode,
                                'observed': observed, 'sampled_checks': checks,
                                'joint_sampled_match': all(checks.values())})
    baseline = next(row for row in results if row['upper_return_tied'] and
                    row['cold_mode'] == 'hv_only_grounded')['observed']
    prior_baseline = chosen['stage_20ms']
    for key, tolerance in (('eht_at_collector_peak_v', .02),
                           ('yoke_current_pp_a', 2e-6),
                           ('c21_voltage_at_collector_peak_v', .002)):
        if abs(baseline[key] - prior_baseline[key]) > tolerance:
            raise ValueError(f'baseline differs from sign screen: {key}')
    dependencies = (order.SOURCE_COMPARISON, order.SOURCE_READ,
                    order.SOURCE_ORDER_VARIANT, SIGN, RAIL, BOUNDARY,
                    boost.stage.GRAPH, boost.stage.PARAMETERS,
                    boost.stage.TRANSCRIPTION, boost.stage.MODELS,
                    boost.rail.CATALOG, boost.bridge.MODEL,
                    ROOT / 't3_brimar_boost_boundary_screen.py',
                    ROOT / 't3_loaded_return_screen.py',
                    ROOT / 't3_booster_pin_order_screen.py', Path(__file__))
    return {
        'format': 'dac-monitor-t3-source-order-return-c21-screen-v1',
        'qualification': 'six conditional source-order upper-return/cold-end alternatives at 20 ms; prescribed drive, one TBY7 class yoke and link pair, no periodic or installed-graph qualification',
        'source_pdf_sha256': SOURCE_PDF_SHA256,
        'input_sha256': {str(path.relative_to(ROOT)): sha(path) for path in dependencies},
        'ngspice_sha256': sha(ngspice),
        'candidate_id': candidate['id'],
        'candidate_polarity': candidate['polarity'],
        'fixed_conditions': {'feed_v': feed, 'initial_c21_differential_v': 65,
                             'window_s': [0.019, 0.020], 'yoke_type': 'TBY7',
                             'centering_link_pair': 'E1+E2'},
        'targets': {'eht_v': eht_bounds, 'yoke_current_pp_a': current_bounds,
                    'c21_differential_v': c21_bounds},
        'cases': results,
        'joint_sampled_match_count': sum(row['joint_sampled_match'] for row in results),
        'interpretation': ('This screen varies only the upper-return and high-voltage '
                           'cold-end connections among six labelled alternatives. '
                           'It does not bound the native X2:4 drive or prove T3 internal '
                           'continuity, and 20 ms samples are not a periodic-field test.'),
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
        value = row['observed']
        print(row['upper_return_tied'], row['cold_mode'],
              value['eht_at_collector_peak_v'], value['yoke_current_pp_a'],
              value['c21_voltage_at_collector_peak_v'])
