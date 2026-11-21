"""Screen prescribed V18 base-high sensitivity in the source-order T3 case."""

import argparse
import hashlib
import json
from pathlib import Path
import tempfile

import t3_booster_pin_order_screen as order
import t3_brimar_boost_boundary_screen as boost
import transformer_candidates


ROOT = Path(__file__).resolve().parent
REF = ROOT / 'reference/k7222-11'
OUTPUT = REF / 't3-source-order-base-level-screen.json'
SIGN = REF / 't3-source-order-polarity-screen.json'
RETURN = REF / 't3-source-order-return-c21-screen.json'
LINKS = REF / 'page4-t3-internal-links-comparison.json'
SOURCE_PDF_SHA256 = '3c435063815af483a0fa98823a8a95a4178359e64f759344ee03cc0300e292dd'
BASE_SOURCE = 'Vbase drive 0 PULSE(-2.7 1.3 1u 20n 20n 46.5u 62.5u)'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(ngspice, source_pdf):
    if sha(source_pdf) != SOURCE_PDF_SHA256:
        raise ValueError('K7222.11 source PDF changed')
    comparison = json.loads(order.SOURCE_COMPARISON.read_text())
    links = json.loads(LINKS.read_text())
    if not comparison['passed'] or not links['passed']:
        raise ValueError('page-4 T3 source comparisons are not passing')
    for name, path in (('source_read_sha256', REF / 'page4-t3-internal-links-source-read.json'),
                       ('transcription_sha256', boost.stage.TRANSCRIPTION),
                       ('sheet_sha256', ROOT / 'circuits/k7222-11-horizontal-output.kicad_sch')):
        if links[name] != sha(path):
            raise ValueError(f'T3 conductor comparison is stale: {name}')
    prior = json.loads(RETURN.read_text())
    sign = json.loads(SIGN.read_text())
    for earlier in (prior, sign):
        if earlier['ngspice_sha256'] != sha(ngspice):
            raise ValueError('earlier source-order screen used a different ngspice')
        for name, digest in earlier['input_sha256'].items():
            if sha(ROOT / name) != digest:
                raise ValueError(f'earlier source-order screen is stale: {name}')
    chosen = next(row for row in sign['candidates']
                  if row['sign_compatible'] and row['polarity']['lower_taps'] == 1
                  and row['polarity']['upper_taps'] == 1)
    inputs = boost.pulse.setup()
    transcription = json.loads(boost.stage.TRANSCRIPTION.read_text())
    alternate, alternate_transcription = order.source_order_inputs(inputs, transcription)
    candidate = next(row for row in transformer_candidates.enumerate_candidates(alternate[0])
                     if row['polarity'] == chosen['polarity'])
    alternate = (alternate[0], alternate[1], candidate, *alternate[3:])
    catalog = json.loads(boost.rail.CATALOG.read_text())
    tby7 = next(row for row in catalog['class_cases'] if row['type'] == 'TBY7')
    yoke = (tby7['line_inductance_h'], tby7['line_resistance_ohm'])
    feed = 42.504
    cases = []
    original_deck = boost.stage.deck
    original_transcription = boost.stage.TRANSCRIPTION
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / 'source-order-transcription.json'
        path.write_text(json.dumps(alternate_transcription))
        try:
            boost.stage.TRANSCRIPTION = path
            for high in (0.8, 1.3, 1.8):
                def adjusted_deck(*args, **kwargs):
                    deck = original_deck(*args, **kwargs)
                    if deck.count(BASE_SOURCE) != 1:
                        raise ValueError('prescribed base source changed')
                    return deck.replace(BASE_SOURCE, BASE_SOURCE.replace(' 1.3 ', f' {high:.1f} '))

                boost.stage.deck = adjusted_deck
                observed = boost.measure(ngspice, alternate, feed, yoke,
                                         initial_boost_node_v=feed + 65,
                                         stop_s=.020, window_start_s=.019)
                targets = prior['targets']
                checks = {
                    'eht': targets['eht_v'][0] <= observed['eht_at_collector_peak_v'] <= targets['eht_v'][1],
                    'yoke_current': targets['yoke_current_pp_a'][0] <= observed['yoke_current_pp_a'] <= targets['yoke_current_pp_a'][1],
                    'c21': targets['c21_differential_v'][0] <= observed['c21_voltage_at_collector_peak_v'] <= targets['c21_differential_v'][1],
                }
                cases.append({'prescribed_base_high_v': high, 'observed': observed,
                              'sampled_checks': checks, 'joint_sampled_match': all(checks.values())})
        finally:
            boost.stage.deck = original_deck
            boost.stage.TRANSCRIPTION = original_transcription
    baseline = next(row for row in prior['cases'] if row['upper_return_tied'] and
                    row['cold_mode'] == 'hv_only_grounded')['observed']
    measured = next(row for row in cases if row['prescribed_base_high_v'] == 1.3)['observed']
    for key, tolerance in (('eht_at_collector_peak_v', .02),
                           ('yoke_current_pp_a', 2e-6),
                           ('c21_voltage_at_collector_peak_v', .002)):
        if abs(measured[key] - baseline[key]) > tolerance:
            raise ValueError(f'baseline differs from return screen: {key}')
    dependencies = (order.SOURCE_COMPARISON, order.SOURCE_READ,
                    order.SOURCE_ORDER_VARIANT, LINKS, SIGN, RETURN,
                    boost.stage.GRAPH, boost.stage.PARAMETERS,
                    boost.stage.TRANSCRIPTION, boost.stage.MODELS,
                    boost.rail.CATALOG, boost.bridge.MODEL,
                    ROOT / 't3_brimar_boost_boundary_screen.py',
                    ROOT / 't3_booster_pin_order_screen.py', Path(__file__))
    return {
        'format': 'dac-monitor-t3-source-order-base-level-screen-v1',
        'qualification': 'three 20 ms prescribed V18 base-high sensitivity cases at one source-order T3 sign/return/TBY7 condition; no installed base drive or periodic qualification',
        'source_pdf_sha256': SOURCE_PDF_SHA256,
        'input_sha256': {str(path.relative_to(ROOT)): sha(path) for path in dependencies},
        'ngspice_sha256': sha(ngspice),
        'candidate_id': candidate['id'],
        'candidate_polarity': candidate['polarity'],
        'fixed_conditions': {'feed_v': feed, 'initial_c21_differential_v': 65,
                             'upper_return_tied': True, 'cold_mode': 'hv_only_grounded',
                             'yoke_type': 'TBY7', 'centering_link_pair': 'E1+E2',
                             'base_low_v': -2.7, 'base_on_time_us': 46.5,
                             'base_period_us': 62.5, 'window_s': [.019, .020]},
        'targets': prior['targets'],
        'cases': cases,
        'joint_sampled_match_count': sum(row['joint_sampled_match'] for row in cases),
        'interpretation': ('Changing only the prescribed base-high level across '
                           'these engineering perturbations does not resolve the '
                           'conditional C21 gap. The range is not source-bounded; '
                           'the X2:4/collector drive waveform and T3 winding graph '
                           'still require qualification.'),
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
        observed = row['observed']
        print(row['prescribed_base_high_v'], observed['eht_at_collector_peak_v'],
              observed['yoke_current_pp_a'], observed['c21_voltage_at_collector_peak_v'])
