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
         driver_parts, *, ratio, l4_h, on_trace, trace):
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
    text = text.replace('i(Lhorizontal) v(h_boost)',
                        'i(Lhorizontal) v(h_boost) v(h_outbase) v(h_drivecol)')
    return text


def simulate(graph, parameters, candidate, output_parts, l3_r, l3_l,
             driver_parts, *, ratio, l4_h, on_trace):
    with tempfile.TemporaryDirectory() as directory:
        folder = Path(directory)
        trace = folder/'late.dat'
        circuit = folder/'stage.cir'
        circuit.write_text(deck(graph, parameters, candidate, output_parts,
                                l3_r, l3_l, driver_parts, ratio=ratio,
                                l4_h=l4_h, on_trace=on_trace, trace=trace))
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
    for phase in ('on_trace', 'off_trace'):
        for ratio in (1, 3, 10):
            for l4_h in (5e-6, 50e-6):
                result = simulate(graph, parameters, candidate, output_parts,
                                  l3_r, l3_l, driver_parts, ratio=ratio,
                                  l4_h=l4_h, on_trace=phase == 'on_trace')
                row = {'v13_drive_phase': phase, 't2_primary_secondary_ratio': ratio,
                       'l4_inductance_per_coil_h': l4_h, 'result': result}
                if result['status'] == 'complete':
                    row['conditional_checks'] = {
                        'tp15_driver_swing_in_manual_range': tp15_range[0] <= result['driver_collector_swing_v'] <= tp15_range[1],
                        'eht_final_in_manual_range': manual_eht['minimum'] <= result['eht_final_v'] <= manual_eht['maximum'],
                    }
                rows.append(row)
    complete = [row for row in rows if row['result']['status'] == 'complete']
    nominal = next(row for row in rows if row['v13_drive_phase'] == 'off_trace'
                   and row['t2_primary_secondary_ratio'] == 3
                   and row['l4_inductance_per_coil_h'] == 5e-6)
    return {
        'format': 'dac-monitor-t2-l4-output-stage-sweep-v1',
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
            'The T3/yoke/EHT bench retains its ideal 41 V feed, 65 V boost initialization, unverified T3 graph, 1 nF/200 Mohm EHT load and optional AC winding loss.',
            'The 4–5 ms window is not proved periodic; solver aborts are retained as failures of the candidate bench, not evidence about factory wiring.',
        ],
        'manual_tp15_range_vpp': tp15_range,
        'manual_eht_range_v': [manual_eht['minimum'], manual_eht['maximum']],
        'cases': rows, 'completed_cases': len(complete), 'aborted_cases': len(rows)-len(complete),
        'nominal_off_trace_case': nominal,
        'conditional_tp15_matches': [
            {key: row[key] for key in ('v13_drive_phase', 't2_primary_secondary_ratio', 'l4_inductance_per_coil_h')}
            for row in complete if row['conditional_checks']['tp15_driver_swing_in_manual_range']],
        'conditional_eht_matches': [
            {key: row[key] for key in ('v13_drive_phase', 't2_primary_secondary_ratio', 'l4_inductance_per_coil_h')}
            for row in complete if row['conditional_checks']['eht_final_in_manual_range']],
        'status': 'partial' if len(complete) < len(rows) else 'complete',
        'analysis_valid': nominal['result']['status'] == 'complete' and len(rows) == 12,
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
