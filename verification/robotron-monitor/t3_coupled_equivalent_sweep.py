"""Screen a passive, labelled T3 equivalent against the loaded TP17 stage."""
import argparse
import json
from pathlib import Path

import magnetics
import t3_output_stage_sweep as stage
import t3_tp17_path_sweep as tp17
import transformer_candidates


ROOT = Path(__file__).resolve().parent
CASES = ((2.5, 1000, 100, True), (5, 1000, 100, True),
         (7.5, 1000, 100, True), (10, 1000, 100, True),
         (7.5, 1768, 100, True), (7.5, 2035, 100, True),
         (7.5, 1768, 50, True), (7.5, 1768, 100, False))


def run(ngspice):
    graph = json.loads(stage.GRAPH.read_text())
    parameters = json.loads(stage.PARAMETERS.read_text())
    candidate = next(c for c in transformer_candidates.enumerate_candidates(graph)
                     if c['id'] == tp17.CANDIDATE_ID)
    transcription, parts, l3_r, l3_l = stage.source_parts()
    by_id = {part['source_id']: part for part in transcription['components']}
    parts += [by_id['012-6921:'+name] for name in tp17.SOURCE_PARTS]
    if (by_id['012-6921:V14']['nodes'] != ['h_g1raw', 'h_sync'] or
            by_id['012-6921:C18']['nodes'] != ['h_g1raw', '0'] or
            by_id['012-6921:R28']['nodes'] != ['h_g1raw', 'ug1', '0']):
        raise ValueError('source-connected TP17 load path changed')
    cases = [tp17.run_case(ngspice, graph, parameters, candidate, parts, l3_r,
                           l3_l, turns, 0, backend='coupled', hv_turns=hv_turns,
                           max_step_ns=step, flux_probe=probe)
             for turns, hv_turns, step, probe in CASES]
    core = parameters['core']
    center = core['h_a_per_m'].index(0)
    mu = ((core['b_t'][center+1]-core['b_t'][center]) /
          (core['h_a_per_m'][center+1]-core['h_a_per_m'][center]))
    primary_turns = parameters['groups']['drive'][0]['turns']['value']
    primary_magnetizing_h = (primary_turns**2*core['area_m2']['value']*mu /
                             core['length_m']['value'])
    return {
        'format': 'dac-monitor-t3-coupled-equivalent-sweep-v1',
        'qualification': 'labelled passive T3 equivalent, prescribed-drive 4–5 ms stage screen only; not a native-grid score, sourced T3 winding, or A5 freeze',
        'source_hashes': {str(path.relative_to(ROOT)): tp17.sha256(path)
                          for path in (stage.GRAPH, stage.PARAMETERS,
                                       stage.TRANSCRIPTION, stage.MODELS,
                                       ROOT/'reference/k7222-11/service-observations.json',
                                       ROOT/'reference/k7222-11/design-point.json',
                                       ROOT/'reference/k7222-11/t3-hv-winding-comparator.json',
                                       ROOT/'reference/k7222-11/t3-coupled-equivalent-parameters.json',
                                       ROOT/'magnetics.py',
                                       ROOT/'transformer_candidates.py',
                                       ROOT/'t3_output_stage_sweep.py',
                                       ROOT/'t3_tp17_path_sweep.py',
                                       ROOT/'t3_coupled_equivalent_sweep.py')},
        'ngspice_sha256': tp17.sha256(ngspice),
        'candidate_id': tp17.CANDIDATE_ID,
        'equivalent_stage_label': 'T3_PASSIVE_COUPLED_EQUIVALENT',
        'coupling_coefficient': magnetics.EQUIVALENT_COUPLING,
        'primary_magnetizing_inductance_h': primary_magnetizing_h,
        'magnetizing_source': 'linear slope at origin of the provisional T3 B/H hypothesis',
        'winding_series_loss_leakage_and_capacitance': 'unchanged provisional bounded T3 section parameters',
        'flux_probe_variation': 'The Bflux source only reads coupled-inductor currents; removing it from a stage deck tests numerical sensitivity and does not change the physical winding connections.',
        'source_path_parts': ['012-6921:'+name for name in tp17.SOURCE_PARTS],
        'manual_tp17_guideline_range_vpp': [64, 96],
        'high_voltage_turn_cases': '1000 active hypothesis; 1768 cross-revision comparator; 2035 conditional A5 design-point turn scale',
        'connected_candidate_parameters': 'reference/k7222-11/t3-coupled-equivalent-parameters.json',
        'cases': cases,
        'remaining': ['Qualify source-informed T3 ratios and parasitic bounds',
                      'Repeat with connected native-grid drive and three locked fields',
                      'Check EHT, TP14/TP15/TP17, V18 stress and step-size convergence together'],
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ngspice', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.write_text(json.dumps(run(args.ngspice), indent=2)+'\n')
