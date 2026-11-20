"""Screen unresolved T3 returns in the prescribed-drive loaded TP17 stage.

Every variant is a conditional source-graph alternative. This is neither a
factory winding read nor a periodic connected monitor qualification.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

import t3_output_stage_sweep as stage
import t3_tp17_path_sweep as tp17
import transformer_candidates


ROOT = Path(__file__).resolve().parent
PARAMETERS = ROOT/'reference/k7222-11/t3-coupled-source-overwind-parameters.json'
RETURN_READ = ROOT/'reference/k7222-11/t3-cold-return-matrix.json'
CASES = ((True, 'shared_grounded', 100, True, 90),
         (True, 'hv_only_grounded', 100, True, 90),
         (False, 'shared_grounded', 100, True, 90),
         (False, 'hv_only_grounded', 100, True, 90),
         (True, 'hv_only_grounded', 100, False, 90),
         (True, 'hv_only_grounded', 50, False, 300))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def variant_parts(parts, ports, joined, cold_mode):
    selected = copy.deepcopy(parts)
    t3 = next(part for part in selected if part['source_id'] == '012-6921:T3')
    nodes = dict(zip(ports, t3['nodes']))
    if not joined:
        nodes['X1_3'] = 'h_upper_return'
    if cold_mode == 'shared_grounded':
        nodes['X1_16'] = nodes['X1_7'] = '0'
    elif cold_mode == 'hv_only_grounded':
        nodes['X1_16'] = '0'
        nodes['X1_7'] = 'h_hvcold'
    else:
        raise ValueError('unknown cold-end graph')
    t3['nodes'] = [nodes[port] for port in ports]
    return selected, {port: nodes[port] for port in
                      ('X1_3', 'X2_3', 'X1_7', 'X1_16')}


def run_case(ngspice, graph, parameters, candidate, parts, l3_r, l3_l,
             max_step_ns, flux_probe, timeout_s):
    with tempfile.TemporaryDirectory() as directory:
        trace = Path(directory)/'trace.dat'
        circuit = Path(directory)/'stage.cir'
        original, _ = transformer_candidates.compile_model(graph, candidate,
                                                            parameters, backend='flux')
        coupled, _ = transformer_candidates.compile_model(graph, candidate,
                                                           parameters, backend='coupled')
        if not flux_probe:
            coupled = '\n'.join(line for line in coupled.splitlines()
                                if not line.startswith('Bflux '))+'\n'
        deck = stage.deck(graph, parameters, candidate, parts, l3_r, l3_l, trace)
        if deck.count(original) != 1:
            raise ValueError('stage magnetic model changed')
        deck = deck.replace(original, coupled)
        if max_step_ns != 100:
            if deck.count('tran 100n 5m 4m') != 1:
                raise ValueError('stage timestep anchor changed')
            deck = deck.replace('tran 100n 5m 4m', f'tran {max_step_ns}n 5m 4m')
        if deck.count('.ic v(h_boost)=65') != 1:
            raise ValueError('stage initial-condition anchor changed')
        deck = deck.replace('.ic v(h_boost)=65',
                            '.param horizontal_brightness_fraction=0.5\n'
                            'Rug1 ug1 0 1G\n.ic v(h_boost)=65')
        circuit.write_text(deck)
        result = {'max_step_ns': max_step_ns, 'flux_probe_in_deck': flux_probe,
                  'timeout_s': timeout_s,
                  'normalized_deck_sha256': hashlib.sha256(
                      deck.replace(str(trace), '<trace>').encode()).hexdigest()}
        try:
            process = subprocess.run([str(ngspice), '-b', str(circuit)],
                                     capture_output=True, text=True, timeout=timeout_s)
        except subprocess.TimeoutExpired:
            return {**result, 'status': 'timeout'}
        log = process.stdout+process.stderr
        if (process.returncode or 'tran simulation(s) aborted' in log
                or not trace.is_file()):
            return {**result, 'status': 'aborted',
                    'timestep_too_small': 'Timestep too small' in log}
        measurements = stage.summarize(trace)
        return {**result, 'status': 'complete', 'result': measurements,
                'snapshot_target_overlap':
                64 <= measurements['sync_swing_v'] <= 96 and
                11000 <= measurements['eht_final_v'] <= 12000}


def run(ngspice):
    graph = json.loads(stage.GRAPH.read_text())
    parameters = json.loads(PARAMETERS.read_text())
    source_read = json.loads(RETURN_READ.read_text())
    if (parameters['high_voltage_coupling']['value'] != 0.92 or
            not source_read['model_checks']['upper_return_currently_tied'] or
            not source_read['model_checks']['hv_cold_currently_floating_shared']):
        raise ValueError('source-informed nominal or original return hypothesis changed')
    candidate = next(c for c in transformer_candidates.enumerate_candidates(graph)
                     if c['id'] == tp17.CANDIDATE_ID)
    transcription, parts, l3_r, l3_l = stage.source_parts()
    by_id = {part['source_id']: part for part in transcription['components']}
    parts += [by_id['012-6921:'+name] for name in tp17.SOURCE_PARTS]
    rows = []
    for joined, cold_mode, max_step_ns, flux_probe, timeout_s in CASES:
        selected, pins = variant_parts(parts, transcription['ports'], joined, cold_mode)
        outcome = run_case(ngspice, graph, parameters, candidate, selected,
                           l3_r, l3_l, max_step_ns, flux_probe, timeout_s)
        rows.append({'upper_return_tied': joined, 'cold_mode': cold_mode,
                     'variant_pins': pins, **outcome})
    return {
        'format': 'dac-monitor-t3-loaded-return-screen-v1',
        'qualification': 'conditional return-graph sensitivity on a prescribed-drive 4–5 ms stage; not a source-confirmed winding, periodic field, connected score or A5 freeze',
        'source_hashes': {str(path.relative_to(ROOT)): sha(path) for path in
                          (PARAMETERS, RETURN_READ, stage.GRAPH, stage.TRANSCRIPTION,
                           stage.MODELS, ROOT/'magnetics.py',
                           ROOT/'transformer_candidates.py',
                           ROOT/'t3_output_stage_sweep.py',
                           ROOT/'t3_tp17_path_sweep.py', Path(__file__).resolve())},
        'ngspice_sha256': sha(ngspice),
        'candidate_id': candidate['id'],
        'fixed_parameters': 'source-informed 1768-turn, 440-ohm, 7.5-pF, k=0.92 overwind; other T3 sections and stage loads retain their provisional values',
        'manual_tp17_guideline_range_vpp': [64, 96],
        'manual_eht_range_v': [11000, 12000],
        'cases': rows,
        'interpretation': 'Grounding only X1:16 makes the short-stage tied/open X1:3 return results nearly equal and the 100 ns result probe-insensitive, but the 50 ns probe-free result greatly exceeds TP17, EHT and collector expectations. Grounding both X1:16 and X1:7 does not finish within 90 s. No variant establishes a numerically qualified stage or the factory graph.',
        'remaining': ['Resolve the source graph or carry labelled alternatives.',
                      'Find a timestep-invariant loaded stage before a connected native-grid score.'],
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ngspice', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.write_text(json.dumps(run(args.ngspice), indent=2)+'\n')
