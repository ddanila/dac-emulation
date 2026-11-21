"""Check C21 initial-state sensitivity in one conditional TBY7 return case."""

import hashlib
import json
from pathlib import Path

import t3_brimar_boost_boundary_screen as boost


ROOT = Path(__file__).resolve().parent
REF = ROOT / 'reference/k7222-11'
OUTPUT = REF / 't3-brimar-boost-settling-screen.json'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(ngspice):
    prior = json.loads(boost.OUTPUT.read_text())
    for name, digest in prior['input_sha256'].items():
        if sha(ROOT / name) != digest:
            raise ValueError(f'boost boundary source changed: {name}')
    if prior['ngspice_sha256'] != sha(ngspice):
        raise ValueError('boost boundary ngspice changed')
    feed = prior['fixed_conditions']['feed_v']
    source_band = prior['source_annotated_c21_voltage_v']
    if source_band != [60, 70]:
        raise ValueError('C21 source band changed')
    baseline = next(row for row in prior['cases']
                    if row['upper_return_tied'] and row['cold_mode'] == 'hv_only_grounded')
    if not baseline['prior_current_and_eht_match']:
        raise ValueError('selected return no longer passes sampled current/EHT checks')

    inputs = boost.pulse.setup()
    transcription, parts, _, _ = boost.stage.source_parts()
    by_id = {row['source_id']: row for row in transcription['components']}
    parts += [by_id['012-6921:' + name] for name in boost.tp17.SOURCE_PARTS]
    selected, pins = boost.returns.variant_parts(parts, transcription['ports'],
                                                  True, 'hv_only_grounded')
    variant_inputs = (*inputs[:3], selected, *inputs[4:6], pins)
    catalog = json.loads(boost.rail.CATALOG.read_text())
    tby7 = next(row for row in catalog['class_cases'] if row['type'] == 'TBY7')
    yoke = (tby7['line_inductance_h'], tby7['line_resistance_ohm'])

    cases = []
    for initial, stop, window in ((65, .020, .019),
                                  (feed + 65, .005, .004),
                                  (feed + 65, .020, .019)):
        observed = boost.measure(ngspice, variant_inputs, feed, yoke,
                                 initial_boost_node_v=initial,
                                 stop_s=stop, window_start_s=window)
        cases.append(dict(initial_boost_node_v=initial,
                          initial_c21_differential_v=initial-feed,
                          stop_s=stop, final_window_start_s=window,
                          **observed,
                          within_source_c21_band=(source_band[0] <=
                              observed['c21_voltage_at_collector_peak_v'] <= source_band[1])))
    final = [row for row in cases if row['stop_s'] == .020]
    final_c21_difference = abs(final[0]['c21_voltage_at_collector_peak_v'] -
                               final[1]['c21_voltage_at_collector_peak_v'])
    max_c21_drift = max(abs(row['c21_window_phase_drift_v']) for row in final)
    max_eht_drift = max(abs(row['eht_window_phase_drift_v']) for row in final)
    return dict(
        format='dac-monitor-t3-brimar-boost-settling-screen-v1',
        qualification='one unverified T3 return graph, prescribed base, TBY7 class yoke and fixed rail; initial-state convergence check only, not a periodic installed-stage qualification',
        input_sha256={str(path.relative_to(ROOT)): sha(path) for path in
                      (boost.OUTPUT, boost.rail.CATALOG, boost.stage.GRAPH,
                       boost.stage.PARAMETERS, boost.stage.TRANSCRIPTION,
                       boost.stage.MODELS, ROOT/'t3_brimar_boost_boundary_screen.py',
                       Path(__file__))},
        ngspice_sha256=sha(ngspice),
        fixed_conditions=dict(feed_v=feed, yoke_type='TBY7',
                              upper_return_tied=True, cold_mode='hv_only_grounded',
                              centering_link_pair='E1+E2', max_step_ns=50),
        source_annotated_c21_voltage_v=source_band,
        cases=cases,
        final_20ms_c21_difference_between_initial_states_v=final_c21_difference,
        max_final_1ms_c21_phase_drift_v=max_c21_drift,
        max_final_1ms_eht_phase_drift_v=max_eht_drift,
        interpretation=('Two different C21 initial states approach the same approximately '
                        '24 V differential by 20 ms in this conditional stage, with small '
                        'last-1-ms same-phase drift. The source annotation is 60-70 V '
                        'across C21, so the 5-ms mismatch is not explained by the initial '
                        'C21 voltage in this graph. This does not reject an installed '
                        'return graph: the T3 graph, prescribed drive, yoke transfer and '
                        'centring chokes are unqualified, and three locked native fields '
                        'were not checked.'))


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ngspice', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args()
    report = run(args.ngspice)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print([(row['initial_c21_differential_v'], row['stop_s'],
            row['c21_voltage_at_collector_peak_v']) for row in report['cases']])
