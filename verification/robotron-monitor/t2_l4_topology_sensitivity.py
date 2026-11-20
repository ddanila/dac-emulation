"""Bound the unresolved L4 branch count in the conditional TP15 stage."""
import argparse
import copy
import json
from pathlib import Path
import subprocess
import tempfile

import t2_l4_output_stage_sweep as driver
import t3_output_stage_sweep as stage
import tp15_equivalent_output_stage as tp15
import transformer_candidates


ROOT = Path(__file__).resolve().parent
SOURCE_READ = ROOT/'reference/k7222-11/page3-4-t2-l4-source-read.json'
TOPOLOGIES = ('parallel', 'single', 'series', 'bridge')
RATIOS = (1, 10)


def change_l4(deck, topology):
    original = ('X1124 h_outputbase h_outbase HORIZONTAL_COMPENSATION\n'
                'X1125 h_outputbase h_outbase HORIZONTAL_COMPENSATION')
    if deck.count(original) != 1:
        raise ValueError('source-addressed L4 branch contract changed')
    variants = {
        'parallel': original,
        'single': 'X1124 h_outputbase h_outbase HORIZONTAL_COMPENSATION',
        'series': ('X1124 h_outputbase h_l4_mid HORIZONTAL_COMPENSATION\n'
                   'X1125 h_l4_mid h_outbase HORIZONTAL_COMPENSATION'),
        'bridge': 'Rbypass_l4 h_outputbase h_outbase 1m',
    }
    return deck.replace(original, variants[topology])


def simulate(graph, parameters, candidate, output_parts, l3_r, l3_l,
             driver_parts, *, topology, ratio):
    with tempfile.TemporaryDirectory() as directory:
        folder = Path(directory)
        trace = folder/'late.dat'
        circuit = folder/'stage.cir'
        baseline = tp15.deck(graph, parameters, candidate, output_parts,
                             l3_r, l3_l, driver_parts, trace, ratio=ratio,
                             phase='on_trace', polarity='model')
        circuit.write_text(change_l4(baseline, topology))
        process = subprocess.run(['ngspice', '-b', str(circuit)],
                                 capture_output=True, text=True)
        log = process.stdout+process.stderr
        aborted = (process.returncode != 0 or 'tran simulation(s) aborted' in log
                   or 'Timestep too small' in log or 'Error:' in log)
        if aborted or not trace.is_file():
            return {'status': 'aborted', 'timestep_failure': 'Timestep too small' in log}
        return {'status': 'complete', **stage.summarize(trace,
                                                      expected_end_s=tp15.STOP_S)}


def run():
    graph = json.loads(stage.GRAPH.read_text())
    parameters = copy.deepcopy(json.loads(stage.AC_LOSS.read_text()))
    parameters['groups']['high_voltage'][0]['turns']['value'] = 2035
    _, output_parts, l3_r, l3_l = stage.source_parts()
    driver_parts = driver.source_parts()
    accepted = set(json.loads(stage.SIGN.read_text())['accepted_candidate_ids'])
    candidate = next(item for item in transformer_candidates.enumerate_candidates(graph)
                     if item['id'] in accepted)
    prior = json.loads(tp15.REGISTER.read_text())
    v18 = next(item for item in prior['devices'] if item['id'] == '012-6921:V18')
    reverse_limit = v18['comparison_targets']['VEBO_v']['maximum']
    if reverse_limit != 9:
        raise ValueError('V18 reverse-base comparator changed')
    manual_eht = json.loads(stage.DESIGN.read_text())['high_voltage_ratio']['eht_target_v']
    rows = []
    for topology in TOPOLOGIES:
        for ratio in RATIOS:
            result = simulate(graph, parameters, candidate, output_parts,
                              l3_r, l3_l, driver_parts, topology=topology,
                              ratio=ratio)
            row = {'l4_path': topology, 't2_primary_secondary_ratio': ratio,
                   'result': result}
            if result['status'] == 'complete':
                row['conditional_checks'] = {
                    'v18_reverse_base_within_class_rating': result['output_base_range_v'][0] >= -reverse_limit,
                    'eht_in_manual_range': manual_eht['minimum'] <= result['eht_final_v'] <= manual_eht['maximum'],
                }
            rows.append(row)
    complete = [row for row in rows if row['result']['status'] == 'complete']
    return {
        'format': 'dac-monitor-t2-l4-topology-sensitivity-v1',
        'qualification': 'conditional L4 branch-count sensitivity under prescribed TP15 voltage; no source-validated alternate jumper graph, connected oscillator, native grid or operating-point approval',
        'source_hashes': {str(path.relative_to(ROOT)): stage.sha(path) for path in
            (Path(__file__), SOURCE_READ, driver.ROOT/'t2_l4_output_stage_sweep.py',
             tp15.ROOT/'tp15_equivalent_output_stage.py', stage.GRAPH,
             stage.AC_LOSS, stage.TRANSCRIPTION, stage.PROFILE, stage.MODELS,
             stage.SIGN, stage.DESIGN, tp15.REGISTER)},
        'stage_assumptions': [
            'The 2035-turn T3 candidate, on-trace 45 Vpp ideal TP15 drive, model T2 polarity, 19–20 ms window and all other stage elements are held as in the earlier TP15 sweep.',
            'Parallel is the current selected L4:1/L4:2 path. Single, series and a 1 milliohm bridge are exploratory bounds on the unresolved effective branch impedance, not source-read alternatives or installed settings.',
            'L4:3 remains bypassed in every case; T2 secondary return and T3 winding graph remain unverified.',
        ],
        'hv_turns': 2035,
        'tp15_swing_vpp': 45,
        'v18_reverse_base_class_limit_v': reverse_limit,
        'manual_eht_range_v': [manual_eht['minimum'], manual_eht['maximum']],
        'cases': rows,
        'completed_cases': len(complete),
        'aborted_cases': len(rows)-len(complete),
        'reverse_base_safe_cases': sum(row['conditional_checks']['v18_reverse_base_within_class_rating'] for row in complete),
        'joint_eht_reverse_base_cases': sum(all(row['conditional_checks'].values()) for row in complete),
        'status': 'partial',
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = run()
    args.output.write_text(json.dumps(report, indent=2)+'\n')
    print(f"{report['completed_cases']}/{len(report['cases'])} cases complete; "
          f"reverse-base safe={report['reverse_base_safe_cases']}; "
          f"joint EHT/stress={report['joint_eht_reverse_base_cases']}")
