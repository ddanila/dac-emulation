"""Archive bounded native-grid evidence for the conditional T3 return graph.

Reads a finished runner directory, including an incomplete solver trace.
Every result is diagnostic; a trace prefix is never a periodic-state score.
"""
import argparse
import hashlib
import json
from pathlib import Path

import native_grid_horizontal_chain
import partial_trace_diagnostic
import steady_supply
import t3_tp17_path_sweep


ROOT = Path(__file__).resolve().parent
LABEL = steady_supply.T3_GROUNDED_AC_LOSS_LABEL


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def summarize(run_directory):
    directory = Path(run_directory)
    run = json.loads((directory/'run.json').read_text())
    candidate_id = t3_tp17_path_sweep.CANDIDATE_ID
    if (run['t3_return_variant'] != 'hv-only-grounded' or
            run['magnetic_backend'] != 'coupled' or
            LABEL not in run['equivalent_stages']):
        raise ValueError('not the labelled conditional T3 run')
    candidate = next(row for row in run['candidates']
                     if row['id'] == candidate_id)
    attempt = next(row for row in candidate['attempts'] if row['fields'] == 4)
    trial = directory/candidate_id/'4'
    solve = json.loads((trial/'solve.json').read_text())
    metadata = json.loads((trial/'metadata.json').read_text())
    variant = json.loads((directory/'assembly/t3-return-variant.json').read_text())
    if (metadata['t3_return_variant'] != 'hv-only-grounded' or
            metadata['t3_return_pins'] != variant['selected_pins'] or
            LABEL not in metadata['equivalent_stages'] or
            variant['selected_pins']['X1_16'] != '0' or
            variant['selected_pins']['X1_7'] != 'h_hvcold'):
        raise ValueError('connected trial does not carry the screened return')
    raw = trial/'trace.raw'
    solver_log = (trial/'solver.log').read_text(errors='replace')
    solver_errors = [line.strip() for line in solver_log.splitlines()
                     if 'Timestep too small' in line or
                     'run simulation(s) aborted' in line]
    partial = partial_trace_diagnostic.summarize(raw)
    chain = native_grid_horizontal_chain.summarize(raw)
    if partial['input_sha256'] != chain['input_sha256']:
        raise ValueError('diagnostics read different raw traces')
    bins = []
    for voltage, horizontal in zip(partial['bins'], chain['bins']):
        start = voltage['start_s']
        if start + partial['window_s'] > partial['last_time_s']:
            break
        if voltage['h_sync_min_v'] is None:
            continue
        bins.append({
            'start_s': start,
            'tp17_mapped_swing_vpp': voltage['h_sync_max_v']-voltage['h_sync_min_v'],
            'eht_time_mean_v': voltage['eht_time_mean_v'],
            'eht_range_v': [voltage['eht_min_v'], voltage['eht_max_v']],
            'drive_collector_upcrossings_10v': horizontal['upcrossings']['v(h_drivecol)'],
            'output_collector_upcrossings_100v': horizontal['upcrossings']['v(h_hot)'],
        })
    endpoint = metadata['period_s']*4
    return {
        'format': 'dac-monitor-t3-connected-ac-loss-diagnostic-v1',
        'qualification': 'bounded connected native-grid diagnostic; unfinished prefixes are not steady-state or service-score evidence',
        'source_hashes': {path.name:sha(path) for path in
                          (ROOT/'steady_supply.py', ROOT/'full_path.py',
                           ROOT/'partial_trace_diagnostic.py',
                           ROOT/'native_grid_horizontal_chain.py',
                           ROOT/'t3_connected_ac_loss_diagnostic.py')},
        'run_directory': str(directory),
        'run_status': run['status'],
        'run_elapsed_s': run['elapsed_s'],
        'capture_sha256': run['capture_sha256'],
        'candidate_id': candidate_id,
        'equivalent_stages': run['equivalent_stages'],
        'assembly_hashes': {
            'magnetic_override': run['hashes']['magnetic-override.json'],
            't3_return_variant': run['hashes']['t3-return-variant.json'],
        },
        'variant_pins': variant['selected_pins'],
        'solver': {
            'status': solve['status'],
            'elapsed_s': solve.get('elapsed_s'),
            'timeout': solve.get('timeout'),
            'deck_sha256': sha(trial/'run.cir'),
            'solver_log_sha256': sha(trial/'solver.log'),
            'abort_messages': solver_errors,
            'initial_voltage_guesses': metadata['initial_voltage_guesses'],
            'linear_solver': metadata['linear_solver'],
            'reltol': metadata['reltol'],
            'max_step_s': metadata['max_step_s'],
        },
        'four_field_endpoint_s': endpoint,
        'four_fields_completed': solve['status'] == 'complete' and
                                 partial['last_time_s'] >= endpoint-1e-9,
        'trace': {
            'sha256': partial['input_sha256'],
            'declared_points': partial['declared_points'],
            'complete_rows': partial['complete_rows'],
            'trailing_bytes': partial['trailing_bytes'],
            'last_time_s': partial['last_time_s'],
        },
        'complete_one_ms_bins': bins,
        'settling': attempt.get('settling'),
        'service_score': attempt.get('service_score'),
        'remaining': ['Original return, AC-loss and connected drive are unqualified.',
                      'A full repeated-field solve and independent refinement are required before an A3 score or A5 freeze.'],
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-directory', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.write_text(json.dumps(summarize(args.run_directory), indent=2)+'\n')
