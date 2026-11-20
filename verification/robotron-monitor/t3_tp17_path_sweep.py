"""Diagnostic TP17 winding/load sweep on the prescribed-drive output stage."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

import t3_output_stage_sweep as stage
import transformer_candidates


ROOT = Path(__file__).resolve().parent
CANDIDATE_ID = 't3-fc941ad61c50ce31'
SOURCE_PARTS = ('C18', 'V14', 'R28')
CASES = ((2.5, 0), (2.5, 1), (2.5, 10), (5, 10), (10, 10))


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_case(ngspice, graph, parameters, candidate, parts, l3_r, l3_l,
             turns, capacitor_esr_ohm, *, backend='flux', hv_turns=None,
             max_step_ns=100, flux_probe=True):
    if max_step_ns not in (50, 100):
        raise ValueError('stage diagnostic supports only 50 or 100 ns steps')
    if backend != 'coupled' and not flux_probe:
        raise ValueError('flux probe variation only applies to coupled backend')
    winding = copy.deepcopy(parameters)
    winding['groups']['auxiliary'][0]['turns']['value'] = turns
    if hv_turns is not None:
        winding['groups']['high_voltage'][0]['turns']['value'] = hv_turns
    selected = copy.deepcopy(parts)
    if capacitor_esr_ohm:
        capacitor = next(part for part in selected if part['source_id'] == '012-6921:C18')
        capacitor['nodes'][0] = 'h_g1cap'
    with tempfile.TemporaryDirectory() as directory:
        trace = Path(directory)/'trace.dat'
        circuit = Path(directory)/'stage.cir'
        deck = stage.deck(graph, winding, candidate, selected, l3_r, l3_l, trace)
        if max_step_ns != 100:
            anchor = 'tran 100n 5m 4m'
            if deck.count(anchor) != 1:
                raise ValueError('stage deck timestep anchor changed')
            deck = deck.replace(anchor, f'tran {max_step_ns}n 5m 4m')
        if backend != 'flux':
            flux, _ = transformer_candidates.compile_model(graph, candidate, winding,
                                                            backend='flux')
            substitute, _ = transformer_candidates.compile_model(graph, candidate,
                                                                  winding, backend=backend)
            if not flux_probe:
                substitute = '\n'.join(line for line in substitute.splitlines()
                                       if not line.startswith('Bflux '))+'\n'
            if deck.count(flux) != 1:
                raise ValueError('stage deck magnetic model changed')
            deck = deck.replace(flux, substitute)
        extra = '.param horizontal_brightness_fraction=0.5\nRug1 ug1 0 1G\n'
        if capacitor_esr_ohm:
            extra += f'Resr h_g1raw h_g1cap {capacitor_esr_ohm:g}\n'
        anchor = '.ic v(h_boost)=65'
        if deck.count(anchor) != 1:
            raise ValueError('stage deck initial-condition anchor changed')
        deck = deck.replace(anchor, extra+anchor)
        circuit.write_text(deck)
        outcome = {'auxiliary_x2_5_to_x2_6_turns': turns,
                   'high_voltage_turns': winding['groups']['high_voltage'][0]['turns']['value'],
                   'max_step_ns': max_step_ns,
                   'flux_probe_in_deck': flux_probe,
                   'c18_series_resistance_ohm': capacitor_esr_ohm,
                   'magnetic_backend': backend,
                   'normalized_deck_sha256': hashlib.sha256(
                       deck.replace(str(trace), '<trace>').encode()).hexdigest()}
        try:
            result = subprocess.run([str(ngspice), '-b', str(circuit)],
                                    capture_output=True, text=True, timeout=90)
        except subprocess.TimeoutExpired:
            outcome['status'] = 'timeout'
            return outcome
        log = result.stdout+result.stderr
        if result.returncode or 'tran simulation(s) aborted' in log or not trace.is_file():
            outcome['status'] = 'aborted'
            outcome['timestep_too_small'] = 'Timestep too small' in log
        else:
            outcome['status'] = 'complete'
            outcome['result'] = stage.summarize(trace)
        return outcome


def run(ngspice):
    graph = json.loads(stage.GRAPH.read_text())
    parameters = json.loads(stage.PARAMETERS.read_text())
    candidate = next(c for c in transformer_candidates.enumerate_candidates(graph)
                     if c['id'] == CANDIDATE_ID)
    transcription, parts, l3_r, l3_l = stage.source_parts()
    by_id = {part['source_id']: part for part in transcription['components']}
    parts += [by_id['012-6921:'+name] for name in SOURCE_PARTS]
    if (by_id['012-6921:V14']['nodes'] != ['h_g1raw', 'h_sync'] or
            by_id['012-6921:C18']['nodes'] != ['h_g1raw', '0'] or
            by_id['012-6921:R28']['nodes'] != ['h_g1raw', 'ug1', '0']):
        raise ValueError('source-connected TP17 load path changed')
    cases = [run_case(ngspice, graph, parameters, candidate, parts, l3_r, l3_l,
                      turns, esr) for turns, esr in CASES]
    return {
        'format': 'dac-monitor-t3-tp17-path-sweep-v1',
        'qualification': 'prescribed-drive 4–5 ms stage diagnostic only; no native-grid waveform score or physical C18 ESR claim',
        'source_hashes': {str(path.relative_to(ROOT)): sha256(path)
                          for path in (stage.GRAPH, stage.PARAMETERS,
                                       stage.TRANSCRIPTION, stage.MODELS,
                                       ROOT/'reference/k7222-11/service-observations.json',
                                       ROOT/'magnetics.py',
                                       ROOT/'transformer_candidates.py',
                                       ROOT/'t3_output_stage_sweep.py',
                                       ROOT/'t3_tp17_path_sweep.py')},
        'ngspice_sha256': sha256(ngspice),
        'candidate_id': CANDIDATE_ID,
        'source_path_parts': ['012-6921:'+name for name in SOURCE_PARTS],
        'manual_tp17_swing_vpp': 80,
        'manual_tp17_guideline_range_vpp': [64, 96],
        'c18_esr_status': 'deliberate numerical sensitivity assumption, not a sourced capacitor specification',
        'cases': cases,
        'interpretation_limit': 'A failed 5 ms solve cannot establish a turns-ratio limit, and a completed prescribed-drive solve cannot qualify sustained native-grid operation.',
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ngspice', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.write_text(json.dumps(run(args.ngspice), indent=2)+'\n')
