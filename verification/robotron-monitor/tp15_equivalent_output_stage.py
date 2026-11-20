"""Stress-audit a prescribed TP15 boundary against the conditional T2/T3 stage."""
import argparse
import copy
import json
from pathlib import Path
import subprocess
import tempfile

import t2_l4_output_stage_sweep as driver
import t3_output_stage_sweep as stage
import transformer_candidates


ROOT = Path(__file__).resolve().parent
REGISTER = ROOT/'reference/k7222-11/device-model-register.json'
TURNS = (1768, 2035, 2409)
RATIOS = (1, 3, 10)
PHASES = ('on_trace', 'off_trace')
POLARITIES = ('model', 'reversed')
TP15_SWING_V = 45
STOP_S = .02
WINDOW_START_S = .019


def deck(graph, parameters, candidate, output_parts, l3_r, l3_l,
         driver_parts, trace, *, ratio, phase, polarity):
    text = driver.deck(graph, parameters, candidate, output_parts, l3_r, l3_l,
                       driver_parts, ratio=ratio, l4_h=5e-6,
                       on_trace=phase == 'on_trace',
                       secondary_reversed=polarity == 'reversed', trace=trace)
    lines = text.splitlines()
    for prefix in ('Vb13 ', 'Rdrive13 ', 'Q1036 '):
        if sum(line.startswith(prefix) for line in lines) != 1:
            raise ValueError('source-connected V13 driver boundary changed: '+prefix)
    lines = [line for line in lines
             if not line.startswith(('Vb13 ', 'Rdrive13 ', 'Q1036 '))]
    pulse = ('PULSE(0 45 1u 20n 20n 46.5u 62.5u)' if phase == 'on_trace' else
             'PULSE(45 0 1u 20n 20n 46.5u 62.5u)')
    lines.insert(1, 'Vtp15 h_drivecol 0 '+pulse)
    text = '\n'.join(lines)+'\n'
    old = 'tran 100n 5m 4m'
    if text.count(old) != 1:
        raise ValueError('output-stage solve window changed')
    return text.replace(old, 'tran 100n 20m 19m')


def simulate(graph, parameters, candidate, output_parts, l3_r, l3_l,
             driver_parts, *, ratio, phase, polarity):
    with tempfile.TemporaryDirectory() as directory:
        folder = Path(directory)
        trace = folder/'late.dat'
        circuit = folder/'stage.cir'
        circuit.write_text(deck(graph, parameters, candidate, output_parts,
                                l3_r, l3_l, driver_parts, trace, ratio=ratio,
                                phase=phase, polarity=polarity))
        process = subprocess.run(['ngspice', '-b', str(circuit)],
                                 capture_output=True, text=True)
        log = process.stdout + process.stderr
        aborted = (process.returncode != 0 or 'tran simulation(s) aborted' in log
                   or 'Timestep too small' in log or 'Error:' in log)
        if aborted or not trace.is_file():
            return {'status': 'aborted',
                    'timestep_failure': 'Timestep too small' in log}
        return {'status': 'complete',
                **stage.summarize(trace, expected_end_s=STOP_S)}


def run():
    graph = json.loads(stage.GRAPH.read_text())
    initial = json.loads(stage.AC_LOSS.read_text())
    _, output_parts, l3_r, l3_l = stage.source_parts()
    driver_parts = driver.source_parts()
    accepted = set(json.loads(stage.SIGN.read_text())['accepted_candidate_ids'])
    candidate = next(item for item in transformer_candidates.enumerate_candidates(graph)
                     if item['id'] in accepted)
    design = json.loads(stage.DESIGN.read_text())
    manual_eht = design['high_voltage_ratio']['eht_target_v']
    collector = json.loads(stage.OPERATING.read_text())['source']['reported_k7222_collector_pulse_v']
    register = json.loads(REGISTER.read_text())
    v18 = next(item for item in register['devices'] if item['id'] == '012-6921:V18')
    reverse_limit = v18['comparison_targets']['VEBO_v']['maximum']
    if v18['model'] != 'HOR_OUTPUT_N' or reverse_limit != 9:
        raise ValueError('V18 reverse-base class comparator changed')
    rows = []
    for turns in TURNS:
        parameters = copy.deepcopy(initial)
        parameters['groups']['high_voltage'][0]['turns']['value'] = turns
        for polarity in POLARITIES:
            for phase in PHASES:
                for ratio in RATIOS:
                    result = simulate(graph, parameters, candidate, output_parts,
                                      l3_r, l3_l, driver_parts, ratio=ratio,
                                      phase=phase, polarity=polarity)
                    row = {'hv_turns': turns,
                           't2_secondary_polarity': polarity,
                           'tp15_pulse_phase': phase,
                           't2_primary_secondary_ratio': ratio,
                           'result': result}
                    if result['status'] == 'complete':
                        eht = result['eht_final_v']
                        row['conditional_checks'] = {
                            'eht_in_manual_range': manual_eht['minimum'] <= eht <= manual_eht['maximum'],
                            'collector_in_reported_range': collector[0] <= result['collector_peak_v'] <= collector[1],
                            'retrace_within_20pct_of_manual': 12.8 <= result['flyback_width_us_at_10pct_swing_median'] <= 19.2,
                            'late_16_line_eht_drift_below_1pct': abs(result['eht_same_phase_drift_v_over_16_lines']) <= .01*abs(eht),
                            'v18_reverse_base_within_class_rating': result['output_base_range_v'][0] >= -reverse_limit,
                        }
                    rows.append(row)
    complete = [row for row in rows if row['result']['status'] == 'complete']
    matching_voltages = [row for row in complete
                         if row['conditional_checks']['eht_in_manual_range']
                         and row['conditional_checks']['collector_in_reported_range']]
    focus = next(row for row in rows if row['hv_turns'] == 2035
                 and row['t2_secondary_polarity'] == 'model'
                 and row['tp15_pulse_phase'] == 'on_trace'
                 and row['t2_primary_secondary_ratio'] == 1)
    return {
        'format': 'dac-monitor-tp15-equivalent-output-stage-v1',
        'qualification': 'prescribed TP15 voltage boundary and conditional T2/L4/T3/yoke stage; no source-validated driver, original winding graph, native-grid stimulus, periodic field score or safe operating point is established',
        'source_hashes': {str(path.relative_to(ROOT)): stage.sha(path) for path in
            (Path(__file__), driver.ROOT/'t2_l4_output_stage_sweep.py',
             stage.ROOT/'t3_output_stage_sweep.py', stage.GRAPH, stage.AC_LOSS,
             stage.TRANSCRIPTION, stage.PROFILE, stage.MODELS, stage.SIGN,
             stage.DESIGN, stage.OPERATING, REGISTER)},
        'candidate_id': candidate['id'],
        'assumptions': [
            'Replace only V13 and its prescribed base drive with a 0-to-45 V ideal source at the source-addressed TP15/V13 collector boundary; retain T2, L4, V18, T3, rectifiers and the conditional yoke/EHT loads.',
            'Both pulse phases and T2 secondary polarities are tested because their factory relation is unresolved; T2 ratios 1, 3 and 10 span the prior bounded stage sweep.',
            'T3 high-voltage turns 1768 and 2409 are cross-revision winding comparators; 2035 is the conditional A5 design value. Other T3 parameters use the active unverified graph and loss candidate.',
            'The 19–20 ms trace is 16 lines, not a native-grid field-periodic or thermal steady-state acceptance run.',
            'The level-1 V18 BJT model does not represent destructive emitter-base avalanche; simulated reverse-base voltages beyond the class rating invalidate an apparent voltage match.',
        ],
        'tp15_source_swing_vpp': TP15_SWING_V,
        'manual_tp15_range_vpp': json.loads(driver.T2_DESIGN.read_text())['documented']['tp15_range_vpp'],
        'manual_eht_range_v': [manual_eht['minimum'], manual_eht['maximum']],
        'reported_collector_range_v': collector,
        'manual_retrace_time_us': 16,
        'v18_emitter_base_reverse_class_limit_v': reverse_limit,
        'v18_emitter_base_limit_source': register['sources']['st_bu508af']['url'],
        'solve_window_s': [WINDOW_START_S, STOP_S],
        'cases': rows,
        'completed_cases': len(complete),
        'aborted_cases': len(rows)-len(complete),
        'voltage_match_case_count': len(matching_voltages),
        'voltage_match_cases': matching_voltages,
        'joint_safe_case_count': sum(all(row['conditional_checks'].values()) for row in complete),
        'focus_2035_turn_case': focus,
        'status': 'partial',
        'remaining': ['Resolve the T2 secondary and T3 winding/return graph from source evidence.',
                      'Find a driver/output configuration that meets TP15, EHT and retrace without exceeding the V18 reverse-base class limit.',
                      'Check current, energy, temperature and field-periodic native-grid stress before adopting an equivalent stage.'],
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = run()
    args.output.write_text(json.dumps(report, indent=2)+'\n')
    print(f"{report['completed_cases']}/{len(report['cases'])} cases complete; "
          f"voltage matches={report['voltage_match_case_count']}; "
          f"safe joint matches={report['joint_safe_case_count']}")
