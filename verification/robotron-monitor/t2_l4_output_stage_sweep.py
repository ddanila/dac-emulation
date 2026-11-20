"""Exercise source-connected T2/L4/V13 drive against a loaded T3 output stage."""
import argparse
import copy
import json
from pathlib import Path
import subprocess
import tempfile

import t3_output_stage_sweep as stage
import transformer_candidates

ROOT = Path(__file__).resolve().parent
OSC = ROOT/'reference/k7222-11/horizontal-transcription.json'
OUTPUT = stage.TRANSCRIPTION
T2_DESIGN = ROOT/'reference/k7222-11/horizontal-t2-design.json'
L4_DESIGN = ROOT/'reference/k7222-11/horizontal-l4-design.json'
PRIMARY_PARTS = ('R23', 'C23', 'R33', 'C24', 'R34', 'V13', 'T2')
BASE_PARTS = ('L4:1', 'L4:2')


def source_parts():
    primary = {part['source_id']: part for part in json.loads(OSC.read_text())['components']}
    output = {part['source_id']: part for part in json.loads(OUTPUT.read_text())['components']}
    selected = [primary[f'012-6921:{name}'] for name in PRIMARY_PARTS]
    selected += [output[f'012-6921:{name}'] for name in BASE_PARTS]
    t2 = primary['012-6921:T2']
    if t2['nodes'] != ['h_drivetop', 'h_drivecol', 'h_outputbase', '0']:
        raise ValueError('source T2 terminal contract changed')
    if any(output[f'012-6921:{name}']['nodes'] != ['h_outputbase', 'h_outbase']
           for name in BASE_PARTS):
        raise ValueError('selected parallel L4 base path changed')
    return selected


def deck(graph, parameters, candidate, output_parts, l3_r, l3_l,
         driver_parts, *, ratio, l4_h, on_trace, secondary_reversed, trace,
         reltol=.001):
    text = stage.deck(graph, parameters, candidate, output_parts, l3_r, l3_l, trace)
    old = ('Vbase drive 0 PULSE(-2.7 1.3 1u 20n 20n 46.5u 62.5u)\n'
           'Rbase drive h_outbase 1')
    if text.count(old) != 1:
        raise ValueError('prescribed V18 base drive changed')
    profile = json.loads(stage.PROFILE.read_text())['parameters']
    values = {key: profile[key]['nominal'] for key in
        ('horizontal_driver_l', 'horizontal_driver_r', 'horizontal_secondary_r',
         'horizontal_driver_coupling', 'horizontal_compensation_r')}
    parameters_line = ' '.join(f'{key}={value:.15g}' for key, value in values.items())
    pulse = ('PULSE(0 1.3 1u 20n 20n 46.5u 62.5u)' if on_trace else
             'PULSE(1.3 0 1u 20n 20n 46.5u 62.5u)')
    lines = [f'.param {parameters_line} horizontal_driver_ratio={ratio} '
             f'horizontal_compensation_l={l4_h:.15g}',
             'V22 p22 0 22', f'Vb13 drive13 0 {pulse}',
             'Rdrive13 drive13 h_drivebase 10']
    lines += [' '.join([part['reference'], *part['nodes'], part['value']])
              for part in driver_parts]
    text = text.replace(old, '\n'.join(lines))
    if secondary_reversed:
        original = 'Ls ground s {horizontal_driver_l/horizontal_driver_ratio^2}'
        if text.count(original) != 1:
            raise ValueError('T2 secondary model changed')
        text = text.replace(original,
                            'Ls s ground {horizontal_driver_l/horizontal_driver_ratio^2}')
    text = text.replace('i(Lhorizontal) v(h_boost)',
                        'i(Lhorizontal) v(h_boost) v(h_outbase) v(h_drivecol)')
    original_options = '.options reltol=.001 abstol=1e-9 method=gear'
    if text.count(original_options) != 1 or reltol not in (.001, .002):
        raise ValueError('output-stage solver contract changed')
    text = text.replace(original_options,
                        f'.options reltol={reltol:.3g} abstol=1e-9 method=gear')
    return text


def simulate(graph, parameters, candidate, output_parts, l3_r, l3_l,
             driver_parts, *, ratio, l4_h, on_trace, secondary_reversed=False,
             reltol=.001):
    with tempfile.TemporaryDirectory() as directory:
        folder = Path(directory)
        trace = folder/'late.dat'
        circuit = folder/'stage.cir'
        circuit.write_text(deck(graph, parameters, candidate, output_parts,
                                l3_r, l3_l, driver_parts, ratio=ratio,
                                l4_h=l4_h, on_trace=on_trace,
                                secondary_reversed=secondary_reversed, trace=trace,
                                reltol=reltol))
        process = subprocess.run(['ngspice', '-b', str(circuit)],
                                 capture_output=True, text=True)
        log = process.stdout + process.stderr
        aborted = (process.returncode != 0 or 'tran simulation(s) aborted' in log
                   or 'Timestep too small' in log or 'Error:' in log)
        if aborted or not trace.is_file():
            return {'status': 'aborted', 'timestep_failure': 'Timestep too small' in log}
        return {'status': 'complete', **stage.summarize(trace)}


def run():
    graph = json.loads(stage.GRAPH.read_text())
    parameters = copy.deepcopy(json.loads(stage.AC_LOSS.read_text()))
    parameters['groups']['high_voltage'][0]['turns']['value'] = 1768
    _, output_parts, l3_r, l3_l = stage.source_parts()
    driver_parts = source_parts()
    accepted = set(json.loads(stage.SIGN.read_text())['accepted_candidate_ids'])
    candidate = next(item for item in transformer_candidates.enumerate_candidates(graph)
                     if item['id'] in accepted)
    tp15_range = json.loads(T2_DESIGN.read_text())['documented']['tp15_range_vpp']
    manual_eht = json.loads(stage.DESIGN.read_text())['high_voltage_ratio']['eht_target_v']
    rows = []
    for polarity in ('model', 'reversed'):
        for phase in ('on_trace', 'off_trace'):
            for ratio in (1, 3, 10):
                for l4_h in (5e-6, 50e-6):
                    common = dict(ratio=ratio, l4_h=l4_h,
                                  on_trace=phase == 'on_trace',
                                  secondary_reversed=polarity == 'reversed')
                    strict = simulate(graph, parameters, candidate, output_parts,
                                      l3_r, l3_l, driver_parts, **common)
                    relaxed = simulate(graph, parameters, candidate, output_parts,
                                       l3_r, l3_l, driver_parts, **common,
                                       reltol=.002)
                    result = strict if strict['status'] == 'complete' else relaxed
                    row = {'t2_secondary_polarity': polarity,
                           'v13_drive_phase': phase,
                           't2_primary_secondary_ratio': ratio,
                           'l4_inductance_per_coil_h': l4_h,
                           'solver': {'strict_reltol': .001,
                                      'strict_status': strict['status'],
                                      'relaxed_reltol': .002,
                                      'relaxed_status': relaxed['status'],
                                      'selected_reltol': .001 if strict['status'] == 'complete' else .002},
                           'result': result}
                    if strict['status'] == relaxed['status'] == 'complete':
                        row['solver']['strict_relaxed_relative_difference'] = {
                            key: abs(strict[key]-relaxed[key])/max(abs(strict[key]), 1e-12)
                            for key in ('driver_collector_swing_v', 'eht_final_v',
                                        'collector_peak_v')}
                    if result['status'] == 'complete':
                        row['conditional_checks'] = {
                            'tp15_driver_swing_in_manual_range': tp15_range[0] <= result['driver_collector_swing_v'] <= tp15_range[1],
                            'eht_final_in_manual_range': manual_eht['minimum'] <= result['eht_final_v'] <= manual_eht['maximum'],
                        }
                    rows.append(row)
    complete = [row for row in rows if row['result']['status'] == 'complete']
    compared = [row['solver']['strict_relaxed_relative_difference'] for row in rows
                if 'strict_relaxed_relative_difference' in row['solver']]
    agreement = {key: max(case[key] for case in compared) for key in
                 ('driver_collector_swing_v', 'eht_final_v', 'collector_peak_v')}
    nominal = next(row for row in rows if row['t2_secondary_polarity'] == 'model'
                   and row['v13_drive_phase'] == 'off_trace'
                   and row['t2_primary_secondary_ratio'] == 3
                   and row['l4_inductance_per_coil_h'] == 5e-6)
    return {
        'format': 'dac-monitor-t2-l4-output-stage-sweep-v2',
        'qualification': 'source-addressed T2/L4/V13-to-V18 output-stage sensitivity with prescribed V13 drive; not connected oscillator, native sync, source-validated page-3/4 seam, periodic monitor or A3/A5 pass',
        'source_hashes': {path.name: stage.sha(path) for path in
            (OSC, OUTPUT, T2_DESIGN, L4_DESIGN, stage.GRAPH, stage.AC_LOSS,
             stage.PROFILE, stage.MODELS, stage.SIGN, stage.DESIGN)},
        'driver_source_parts': [part['source_id'] for part in driver_parts],
        't3_candidate_id': candidate['id'], 'high_voltage_turns': 1768,
        'stage_assumptions': [
            'T2 primary and V13 collector use source-transcribed R23/C23/R33/C24/V13/T2 branches; two L4 sections connect its secondary to V18 base in the selected E2 configuration.',
            'V13 base is forced by either on-trace or off-trace 1.3 V/0 V pulses through 10 ohms; oscillator, V12 and exact native phase are absent.',
            'T2 ratio and L4 inductance use declared parameter endpoints; primary coupling, resistance and L4 resistance stay at their provisional nominal values.',
            'T2 secondary terminal polarity is not resolved by the source page-3/4 seam; both the active model direction and its reversal are simulated without claiming either is factory wiring.',
            'The T3/yoke/EHT bench retains its ideal 41 V feed, 65 V boost initialization, unverified T3 graph, 1 nF/200 Mohm EHT load and optional AC winding loss.',
            'The 4–5 ms window is not proved periodic. Cases that abort at reltol 0.001 are retried at 0.002 with the same Gear method; strict/relaxed agreement is checked where both complete.',
        ],
        'manual_tp15_range_vpp': tp15_range,
        'manual_eht_range_v': [manual_eht['minimum'], manual_eht['maximum']],
        'cases': rows, 'completed_cases': len(complete), 'aborted_cases': len(rows)-len(complete),
        'strict_completed_cases': sum(row['solver']['strict_status'] == 'complete' for row in rows),
        'relaxed_completed_cases': sum(row['solver']['relaxed_status'] == 'complete' for row in rows),
        'strict_relaxed_comparison_cases': len(compared),
        'strict_relaxed_max_relative_difference': agreement,
        'strict_relaxed_within_2pct': all(value <= .02 for value in agreement.values()),
        'nominal_off_trace_case': nominal,
        'conditional_tp15_matches': [
            {key: row[key] for key in ('t2_secondary_polarity', 'v13_drive_phase', 't2_primary_secondary_ratio', 'l4_inductance_per_coil_h')}
            for row in complete if row['conditional_checks']['tp15_driver_swing_in_manual_range']],
        'conditional_eht_matches': [
            {key: row[key] for key in ('t2_secondary_polarity', 'v13_drive_phase', 't2_primary_secondary_ratio', 'l4_inductance_per_coil_h')}
            for row in complete if row['conditional_checks']['eht_final_in_manual_range']],
        'status': 'partial' if len(complete) < len(rows) else 'complete',
        'analysis_valid': nominal['result']['status'] == 'complete' and len(rows) == 24
                          and len(compared) > 0 and all(value <= .02 for value in agreement.values()),
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = run()
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(f"{report['completed_cases']}/{len(report['cases'])} cases complete; TP15 matches={len(report['conditional_tp15_matches'])}; EHT matches={len(report['conditional_eht_matches'])}")
    if not report['analysis_valid']:
        raise SystemExit(1)
