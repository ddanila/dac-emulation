"""Screen TP15 amplitude and HV turns at the conditional L4 bridge boundary."""
import argparse
import copy
import json
from pathlib import Path
import subprocess
import tempfile

import t2_l4_topology_sensitivity as l4
import transformer_candidates


ROOT = Path(__file__).resolve().parent
REPORT = ROOT/'reference/k7222-11/t2-l4-bridge-drive-sensitivity.json'
POINTS = ((2035, 36), (2035, 45), (2035, 48), (2035, 51),
          (2035, 54), (2300, 45), (2409, 45))
PULSE = 'Vtp15 h_drivecol 0 PULSE(0 45 1u 20n 20n 46.5u 62.5u)'


def simulate(graph, initial, candidate, output_parts, l3_r, l3_l,
             driver_parts, turns, amplitude):
    parameters = copy.deepcopy(initial)
    parameters['groups']['high_voltage'][0]['turns']['value'] = turns
    with tempfile.TemporaryDirectory() as directory:
        trace = Path(directory)/'late.dat'
        circuit = Path(directory)/'stage.cir'
        deck = l4.tp15.deck(graph, parameters, candidate, output_parts,
                            l3_r, l3_l, driver_parts, trace, ratio=10,
                            phase='on_trace', polarity='model')
        deck = l4.change_l4(deck, 'bridge')
        if deck.count(PULSE) != 1:
            raise ValueError('prescribed TP15 drive boundary changed')
        circuit.write_text(deck.replace(
            PULSE, PULSE.replace('PULSE(0 45 ', f'PULSE(0 {amplitude} ')))
        process = subprocess.run(['ngspice', '-b', str(circuit)],
                                 capture_output=True, text=True)
        log = process.stdout + process.stderr
        aborted = (process.returncode != 0 or 'tran simulation(s) aborted' in log
                   or 'Timestep too small' in log or 'Error:' in log)
        if aborted or not trace.is_file():
            return {'status': 'aborted',
                    'timestep_failure': 'Timestep too small' in log}
        return {'status': 'complete',
                **l4.stage.summarize(trace, expected_end_s=l4.tp15.STOP_S)}


def run():
    stage = l4.stage
    graph = json.loads(stage.GRAPH.read_text())
    initial = json.loads(stage.AC_LOSS.read_text())
    _, output_parts, l3_r, l3_l = stage.source_parts()
    driver_parts = l4.driver.source_parts()
    accepted = set(json.loads(stage.SIGN.read_text())['accepted_candidate_ids'])
    candidate = next(item for item in transformer_candidates.enumerate_candidates(graph)
                     if item['id'] in accepted)
    design = json.loads(stage.DESIGN.read_text())
    manual_eht = design['high_voltage_ratio']['eht_target_v']
    manual_tp15 = json.loads(l4.driver.T2_DESIGN.read_text())['documented']['tp15_range_vpp']
    register = json.loads(l4.tp15.REGISTER.read_text())
    v18 = next(item for item in register['devices'] if item['id'] == '012-6921:V18')
    reverse_limit = v18['comparison_targets']['VEBO_v']['maximum']
    if reverse_limit != 9:
        raise ValueError('V18 reverse-base comparator changed')
    rows = []
    for turns, amplitude in POINTS:
        result = simulate(graph, initial, candidate, output_parts, l3_r, l3_l,
                          driver_parts, turns, amplitude)
        row = {'hv_turns': turns, 'tp15_source_swing_vpp': amplitude,
               'result': result}
        if result['status'] == 'complete':
            row['conditional_checks'] = {
                'tp15_in_manual_range': manual_tp15[0] <= amplitude <= manual_tp15[1],
                'eht_in_manual_range': manual_eht['minimum'] <= result['eht_final_v'] <= manual_eht['maximum'],
                'v18_reverse_base_within_class_rating': result['output_base_range_v'][0] >= -reverse_limit,
            }
        rows.append(row)
    complete = [row for row in rows if row['result']['status'] == 'complete']
    return {
        'format': 'dac-monitor-t2-l4-bridge-drive-sensitivity-v1',
        'qualification': 'conditional prescribed TP15 stage with exploratory 1 milliohm L4 bridge; neither the installed jumper setting nor a source-driven, field-periodic operating point is qualified',
        'source_hashes': {str(path.relative_to(ROOT)): stage.sha(path) for path in
            (Path(__file__), l4.ROOT/'t2_l4_topology_sensitivity.py',
             l4.tp15.ROOT/'tp15_equivalent_output_stage.py',
             l4.driver.ROOT/'t2_l4_output_stage_sweep.py',
             stage.ROOT/'t3_output_stage_sweep.py', l4.SOURCE_READ,
             stage.GRAPH, stage.AC_LOSS, stage.TRANSCRIPTION, stage.PROFILE,
             stage.MODELS, stage.SIGN, stage.DESIGN, l4.driver.T2_DESIGN,
             l4.tp15.REGISTER)},
        'candidate_id': candidate['id'],
        'assumptions': [
            'The conditional AC-loss T3, on-trace model-polarity TP15 pulse, T2 ratio 10 and 19–20 ms output-stage window are held fixed.',
            'The 1 milliohm L4 bridge is an exploratory lower-impedance bound, not a source-read installed jumper setting.',
            'TP15 amplitudes 36–54 Vpp span the manual tolerance; 2035 HV turns is the conditional design point, 2300 an interior comparator and 2409 a cross-revision comparator.',
            'A late 16-line trace is not a source-connected native-grid field-periodicity or thermal steady-state qualification.',
            'The level-1 V18 BJT lacks reverse emitter-base breakdown, so the 9 V class comparison excludes apparent voltage matches beyond that stress.',
        ],
        'manual_tp15_range_vpp': manual_tp15,
        'manual_eht_range_v': [manual_eht['minimum'], manual_eht['maximum']],
        'v18_reverse_base_class_limit_v': reverse_limit,
        'cases': rows,
        'completed_cases': len(complete),
        'aborted_cases': len(rows)-len(complete),
        'joint_eht_reverse_base_cases': sum(
            row['conditional_checks']['eht_in_manual_range']
            and row['conditional_checks']['v18_reverse_base_within_class_rating']
            for row in complete),
        'status': 'partial',
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=REPORT)
    args = parser.parse_args()
    report = run()
    args.output.write_text(json.dumps(report, indent=2)+'\n')
    print(f"{report['completed_cases']}/{len(report['cases'])} cases complete; "
          f"joint EHT/reverse-base matches={report['joint_eht_reverse_base_cases']}")
