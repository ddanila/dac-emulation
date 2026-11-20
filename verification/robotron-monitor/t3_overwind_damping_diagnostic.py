"""Test whether a hypothetical overwind loss stabilizes the loaded TP17 stage.

The shunt is an artificial diagnostic, not a sourced K7222.11 winding value.
No case here qualifies a periodic connected monitor or freezes T3.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import subprocess
import tempfile

import t3_output_stage_sweep as stage
import t3_tp17_path_sweep as tp17
import transformer_candidates


ROOT = Path(__file__).resolve().parent
PARAMETERS = ROOT/'reference/k7222-11/t3-coupled-source-overwind-parameters.json'
CASES = ((100_000, 100, True), (300_000, 100, True),
         (1_000_000, 100, True), (3_000_000, 100, True),
         (3_000_000, 50, True), (3_000_000, 100, False))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def diagnostic_deck(graph, parameters, candidate, parts, l3_r, l3_l,
                    trace, shunt_ohm, max_step_ns, flux_probe):
    original, _ = transformer_candidates.compile_model(graph, candidate, parameters,
                                                        backend='flux')
    coupled, metadata = transformer_candidates.compile_model(graph, candidate,
                                                               parameters, backend='coupled')
    hv = [i for i, section in enumerate(metadata['sections'])
          if section['group'] == 'high_voltage']
    if len(hv) != 1:
        raise ValueError('expected one high-voltage winding section')
    index = hv[0]
    cap = parameters['groups']['high_voltage'][0]['capacitance_f']['value']
    anchor = f'Cw{index} w{index}p w{index}n {cap:.15g}'
    if coupled.count(anchor) != 1:
        raise ValueError('overwind self-capacitance anchor changed')
    coupled = coupled.replace(anchor, anchor+'\n'+
                              f'Rhv_diagnostic w{index}p w{index}n {shunt_ohm:.15g}')
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
    return deck


def run_case(ngspice, graph, parameters, candidate, parts, l3_r, l3_l,
             shunt_ohm, max_step_ns, flux_probe):
    with tempfile.TemporaryDirectory() as directory:
        trace = Path(directory)/'trace.dat'
        circuit = Path(directory)/'stage.cir'
        deck = diagnostic_deck(graph, parameters, candidate, parts, l3_r, l3_l,
                               trace, shunt_ohm, max_step_ns, flux_probe)
        circuit.write_text(deck)
        row = {'overwind_shunt_ohm': shunt_ohm, 'max_step_ns': max_step_ns,
               'flux_probe_in_deck': flux_probe,
               'normalized_deck_sha256': hashlib.sha256(
                   deck.replace(str(trace), '<trace>').encode()).hexdigest()}
        try:
            process = subprocess.run([str(ngspice), '-b', str(circuit)],
                                     capture_output=True, text=True, timeout=90)
        except subprocess.TimeoutExpired:
            return {**row, 'status': 'timeout'}
        log = process.stdout+process.stderr
        if (process.returncode or 'tran simulation(s) aborted' in log
                or not trace.is_file()):
            return {**row, 'status': 'aborted',
                    'timestep_too_small': 'Timestep too small' in log}
        result = stage.summarize(trace)
        row['status'] = 'complete'
        row['result'] = result
        row['snapshot_target_overlap'] = (
            64 <= result['sync_swing_v'] <= 96 and
            11000 <= result['eht_final_v'] <= 12000)
        return row


def run(ngspice):
    graph = json.loads(stage.GRAPH.read_text())
    parameters = json.loads(PARAMETERS.read_text())
    if parameters['high_voltage_coupling']['value'] != 0.92:
        raise ValueError('nominal overwind coupling changed')
    candidate = next(c for c in transformer_candidates.enumerate_candidates(graph)
                     if c['id'] == tp17.CANDIDATE_ID)
    transcription, parts, l3_r, l3_l = stage.source_parts()
    by_id = {part['source_id']: part for part in transcription['components']}
    parts += [by_id['012-6921:'+name] for name in tp17.SOURCE_PARTS]
    turns = parameters['groups']['high_voltage'][0]['turns']['value']
    core = parameters['core']
    center = core['h_a_per_m'].index(0)
    mu = ((core['b_t'][center+1]-core['b_t'][center]) /
          (core['h_a_per_m'][center+1]-core['h_a_per_m'][center]))
    magnetizing = turns**2*core['area_m2']['value']*mu/core['length_m']['value']
    coupling = parameters['high_voltage_coupling']['value']
    explicit_leakage = parameters['groups']['high_voltage'][0]['leakage_h']['value']
    capacitance = parameters['groups']['high_voltage'][0]['capacitance_f']['value']
    leakage_approx = magnetizing*(1-coupling**2)+explicit_leakage
    cases = [run_case(ngspice, graph, parameters, candidate, parts, l3_r, l3_l,
                      *case) for case in CASES]
    coarse = next(row for row in cases if row['overwind_shunt_ohm'] == 3_000_000
                  and row['max_step_ns'] == 100 and row['flux_probe_in_deck'])
    variants = [row for row in cases if row['overwind_shunt_ohm'] == 3_000_000
                and row is not coarse]
    if coarse['status'] != 'complete' or any(row['status'] != 'complete' for row in variants):
        raise ValueError('required numerical-comparison case did not complete')
    tp17_reference = coarse['result']['sync_swing_v']
    numerical_variation = [abs(row['result']['sync_swing_v']-tp17_reference) /
                           tp17_reference for row in variants]
    return {
        'format': 'dac-monitor-t3-overwind-damping-diagnostic-v1',
        'qualification': 'artificial overwind shunt in a prescribed-drive 4–5 ms stage; no physical loss value, periodic operating point, or A5 freeze is claimed',
        'source_hashes': {str(path.relative_to(ROOT)): sha(path) for path in
                          (PARAMETERS, stage.GRAPH, stage.TRANSCRIPTION, stage.MODELS,
                           ROOT/'magnetics.py', ROOT/'transformer_candidates.py',
                           ROOT/'t3_output_stage_sweep.py', ROOT/'t3_tp17_path_sweep.py',
                           Path(__file__).resolve())},
        'ngspice_sha256': sha(ngspice),
        'candidate_id': candidate['id'],
        'source_context': {
            'url': 'https://www.worldphaco.com/uploads/BUSH_TV22.pdf',
            'observation': 'Firsthand CRT LOPT study attributes apparent overwind resonance during scan to self-capacitance and leakage inductance, not the full magnetizing inductance; not a K7222.11 measurement.'},
        'lumped_two_winding_estimate': {
            'magnetizing_inductance_h': magnetizing,
            'coupling_coefficient': coupling,
            'coupling_leakage_h_approx': magnetizing*(1-coupling**2),
            'explicit_series_leakage_h': explicit_leakage,
            'combined_leakage_h_approx': leakage_approx,
            'overwind_capacitance_f': capacitance,
            'leakage_capacitance_resonance_hz_approx': 1/(2*math.pi*math.sqrt(leakage_approx*capacitance)),
            'limit': 'Two-winding estimate only; the actual 14-section, switched, rectified stage has multiple resonances.'},
        'cases': cases,
        'max_fractional_tp17_change_from_step_or_probe': max(numerical_variation),
        'numerical_qualification': 'failed: the apparent joint-target snapshot changes by more than a factor of nine under half timestep or removal of a non-driving probe',
        'remaining': ['Resolve or bound the original T3 tap/return graph and its loss mechanism.',
                      'Find a step- and probe-invariant stage candidate before a connected native-grid run.'],
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ngspice', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.write_text(json.dumps(run(args.ngspice), indent=2)+'\n')
