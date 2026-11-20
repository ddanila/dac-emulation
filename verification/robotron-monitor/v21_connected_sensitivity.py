"""Bound V21's effect in the conditional, loaded T2/L4/T3 stage bench."""
import argparse
import copy
import json
import math
from pathlib import Path
import re
import subprocess
import tempfile

import t2_l4_output_stage_sweep as driver
import t3_output_stage_sweep as stage
import transformer_candidates

ROOT = Path(__file__).resolve().parent
REGISTER = ROOT/'reference/k7222-11/device-model-register.json'
STAGE_REPORT = ROOT/'reference/k7222-11/t2-l4-output-stage-sweep.json'
MODEL_LINE = re.compile(r'^\.model HOR_HV_RECT D\([^\n]+\)$', re.MULTILINE)
PARAMETERS = ('IS', 'N', 'RS', 'CJO', 'TT', 'BV', 'IBV', 'VJ', 'M', 'FC', 'EG', 'XTI')


def setup():
    graph = json.loads(stage.GRAPH.read_text())
    parameters = copy.deepcopy(json.loads(stage.AC_LOSS.read_text()))
    parameters['groups']['high_voltage'][0]['turns']['value'] = 1768
    _, output_parts, l3_r, l3_l = stage.source_parts()
    driver_parts = driver.source_parts()
    accepted = set(json.loads(stage.SIGN.read_text())['accepted_candidate_ids'])
    candidate = next(item for item in transformer_candidates.enumerate_candidates(graph)
                     if item['id'] in accepted)
    device = next(row for row in json.loads(REGISTER.read_text())['devices']
                  if row['id'] == '012-6921:V21')
    values = {row['spice_parameter']: row for row in device['parameters'].values()}
    if set(values) != set(PARAMETERS):
        raise ValueError('V21 register no longer covers the twelve explicit diode parameters')
    live = MODEL_LINE.search(stage.MODELS.read_text())
    if live is None:
        raise ValueError('active V21 model line is missing')
    raw = dict(re.findall(r'([A-Z]+)=([0-9.eE+-]+[pnuk]?)', live.group()))
    scale = {'p': 1e-12, 'n': 1e-9, 'u': 1e-6, 'k': 1e3}
    actual = {key: float(value[:-1])*scale[value[-1]] if value[-1] in scale
              else float(value) for key, value in raw.items()}
    if set(actual) != set(values) or any(not math.isclose(actual[key], values[key]['nominal'], rel_tol=1e-12)
                                         for key in PARAMETERS):
        raise ValueError('V21 register nominal differs from live SPICE model')
    return graph, parameters, candidate, output_parts, l3_r, l3_l, driver_parts, values


def simulate(inputs, overrides, reltol=.002):
    graph, parameters, candidate, output_parts, l3_r, l3_l, driver_parts, values = inputs
    with tempfile.TemporaryDirectory() as directory:
        folder = Path(directory)
        trace, stress, circuit = (folder/name for name in ('late.dat', 'stress.dat', 'stage.cir'))
        deck = driver.deck(graph, parameters, candidate, output_parts, l3_r, l3_l,
                           driver_parts, ratio=3, l4_h=5e-6, on_trace=False,
                           secondary_reversed=False, trace=trace, reltol=reltol)
        nominal = {key: values[key]['nominal'] for key in PARAMETERS}
        nominal.update(overrides)
        model = '.model HOR_HV_RECT D(' + ' '.join(
            f'{key}={nominal[key]:.12g}' for key in PARAMETERS) + ')'
        deck, count = MODEL_LINE.subn(model, deck)
        if count != 1:
            raise ValueError('expected exactly one V21 model line')
        old = 'D1132 h_hvac eht HOR_HV_RECT'
        if deck.count(old) != 1:
            raise ValueError('source V21 branch changed')
        deck = deck.replace(old, 'D1132 h_hvac v21_sense HOR_HV_RECT\nVSENSE v21_sense eht 0')
        before = 'quit\n.endc\n.end'
        if deck.count(before) != 1:
            raise ValueError('stage trace control changed')
        deck = deck.replace(before, f'wrdata {stress} v(h_hvac) v(eht) i(vsense)\n'+before)
        circuit.write_text(deck)
        process = subprocess.run(['ngspice', '-b', str(circuit)],
                                 capture_output=True, text=True)
        log = process.stdout+process.stderr
        if process.returncode or 'tran simulation(s) aborted' in log or 'Timestep too small' in log or not trace.is_file() or not stress.is_file():
            return {'status': 'aborted', 'timestep_failure': 'Timestep too small' in log}
        result = stage.summarize(trace)
        with stress.open() as stream:
            columns = next(stream).split()
            if columns != ['time', 'v(h_hvac)', 'v(eht)', 'i(vsense)']:
                raise ValueError('unexpected V21 stress trace columns')
            samples = [tuple(map(float, line.split())) for line in stream if line.strip()]
        if len(samples) != result['sample_count'] or not all(
                len(row) == 4 and all(math.isfinite(v) for v in row) for row in samples):
            raise ValueError('incomplete V21 stress trace')
        reverse = [eht-anode for _,anode,eht,_ in samples]
        currents = [current for *_,current in samples]
        return {'status': 'complete', 'stage': result,
                'stress': {'late_window_reverse_voltage_peak_v': max(reverse),
                           'late_window_forward_voltage_peak_v': max(-v for v in reverse),
                           'late_window_forward_current_peak_a': max(currents),
                           'late_window_reverse_current_peak_a': max(-v for v in currents),
                           'sample_count': len(samples)}}


def run():
    inputs = setup()
    values = inputs[-1]
    reference = json.loads(STAGE_REPORT.read_text())['nominal_off_trace_case']
    selected_reltol = reference['solver']['selected_reltol']
    if selected_reltol not in (.001, .002):
        raise ValueError('saved nominal T2/L4 solve tolerance changed')
    nominal = simulate(inputs, {})
    if nominal['status'] != 'complete':
        raise RuntimeError('V21 nominal loaded-stage bench did not complete')
    graph, parameters, candidate, output_parts, l3_r, l3_l, driver_parts, _ = inputs
    unsensed = driver.simulate(graph, parameters, candidate, output_parts,
                               l3_r, l3_l, driver_parts, ratio=3, l4_h=5e-6,
                               on_trace=False, reltol=.002)
    if unsensed['status'] != 'complete':
        raise RuntimeError('V21 unsensed comparison did not complete')
    reference_result = reference['result']
    if any(abs(unsensed[key]-reference_result[key]) > .01*max(abs(reference_result[key]), 1e-12)
           for key in ('eht_final_v', 'collector_peak_v', 'driver_collector_swing_v',
                       'flyback_width_us_at_10pct_swing_median')):
        raise ValueError('V21 unsensed comparison differs from saved stage by over 1%')
    probe_relative_difference = {
        key: (nominal['stage'][key]-unsensed[key])/max(abs(unsensed[key]), 1e-12)
        for key in ('eht_final_v', 'collector_peak_v', 'driver_collector_swing_v',
                    'flyback_width_us_at_10pct_swing_median')}
    if any(abs(value) > .01 for value in probe_relative_difference.values()):
        raise ValueError('V21 current probe changes the nominal stage by over 1%')
    rows = []
    for parameter in PARAMETERS:
        for endpoint, value in zip(('low', 'high'), values[parameter]['bounds']):
            result = simulate(inputs, {parameter: value})
            changes = None
            if result['status'] == 'complete':
                base = nominal['stage']; current = result['stage']
                changes = {key: (current[key]-base[key])/max(abs(base[key]), 1e-12)
                           for key in ('eht_final_v', 'collector_peak_v',
                                       'driver_collector_swing_v',
                                       'flyback_width_us_at_10pct_swing_median')}
            rows.append({'parameter': parameter, 'endpoint': endpoint,
                         'value': value, 'result': result,
                         'relative_change': changes})
    complete = [row for row in rows if row['result']['status'] == 'complete']
    max_change = {key: max(abs(row['relative_change'][key]) for row in complete)
                  for key in ('eht_final_v', 'collector_peak_v',
                              'driver_collector_swing_v',
                              'flyback_width_us_at_10pct_swing_median')}
    return {'format': 'dac-monitor-v21-connected-sensitivity-v1',
            'qualification': 'one-at-a-time V21 bounds in a source-addressed but prescribed-V13, unverified-T3, nonperiodic 4-5 ms output-stage bench; not factory V21 identity or sustained monitor stress qualification',
            'source_hashes': {path.name: stage.sha(path) for path in
                (stage.MODELS, REGISTER, stage.TRANSCRIPTION, driver.OSC,
                 stage.GRAPH, stage.AC_LOSS, stage.PROFILE, stage.SIGN, STAGE_REPORT)},
            'stage_case': {'t2_ratio': 3, 'l4_inductance_per_coil_h': 5e-6,
                           'v13_drive_phase': 'off_trace', 't2_secondary_polarity': 'model',
                           'high_voltage_turns': 1768, 'reltol': .002,
                           'sense_element': 'ideal zero-volt source in series with V21'},
            'nominal': nominal,
            'sense_probe_relative_difference_from_unsensed_stage': probe_relative_difference,
            'bounds': rows,
            'completed_bounds': len(complete), 'total_bounds': len(rows),
            'max_absolute_relative_change': max_change,
            'status': 'partial',
            'remaining': ['Resolve factory V21 identity and T3 tap/return graph',
                          'Check joint parameter corners and source-connected native-grid sustained stage stress']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = run()
    args.output.write_text(json.dumps(report, indent=2)+'\n')
    print(f"V21: {report['completed_bounds']}/{report['total_bounds']} bounds complete; "
          f"max EHT change {report['max_absolute_relative_change']['eht_final_v']:.1%}")


if __name__ == '__main__':
    main()
