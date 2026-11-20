"""Reproduce a conditional AC-loss T3 candidate on the loaded TP17 stage.

This prescribed-drive 4–5 ms screen does not qualify the original T3 graph or
a sustained connected monitor. It records a labelled fallback candidate.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path

import t3_loaded_return_screen as returns
import t3_output_stage_sweep as stage
import t3_tp17_path_sweep as tp17
import transformer_candidates


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT/'reference/k7222-11/t3-coupled-source-overwind-parameters.json'
LOSS = stage.AC_LOSS
PARAMETERS = ROOT/'reference/k7222-11/t3-coupled-source-ac-loss-parameters.json'
CASES = ((7.5, 100, False), (7.5, 50, False),
         (8.0, 100, False), (8.0, 50, False),
         (10.0, 100, False), (10.0, 50, False),
         (10.0, 100, True))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def candidate_parameters():
    result = json.loads(SOURCE.read_text())
    loss = json.loads(LOSS.read_text())
    if result['high_voltage_coupling']['value'] != 0.92:
        raise ValueError('overwind coupling changed')
    for group, sections in result['groups'].items():
        comparators = loss['groups'][group]
        if len(sections) != len(comparators):
            raise ValueError('AC-loss section count changed: '+group)
        for section, comparator in zip(sections, comparators):
            for key in ('skin_resistance_ohm', 'skin_fraction'):
                section[key] = copy.deepcopy(comparator[key])
    auxiliary = result['groups']['auxiliary'][0]['turns']
    if not auxiliary['minimum'] <= 10 <= auxiliary['maximum']:
        raise ValueError('10-turn screen outside provisional bounds')
    auxiliary['value'] = 10.0
    auxiliary['rationale'] = ('Upper endpoint of the existing assumed bound. The '
                              'stable 7.5-turn stage gives about 60 Vpp TP17; '
                              '10 turns screen the manual 80 Vpp nominal. This '
                              'is stage-informed tuning, not factory winding data.')
    result['rationale'] = ('Conditional passive T3 equivalent: cross-revision '
                           'overwind plus provisional one-pole AC winding loss. '
                           'The 10-turn auxiliary and grounded HV cold end are '
                           'stage-screen choices; no original T3 or connected '
                           'operating point is frozen.')
    result['source_basis']['ac_loss_candidate'] = 'reference/k7222-11/t3-ac-loss-parameters.json'
    result['source_basis']['ac_loss_limit'] = ('10-ohm low-turn and 5-kohm HV '
                                             'AC-loss proxies and skin fractions '
                                             'are assumed-bound, not measured '
                                             '.11 winding impedances.')
    return result


def run(ngspice):
    parameters = candidate_parameters()
    if json.loads(PARAMETERS.read_text()) != parameters:
        raise ValueError('saved candidate differs from reproducible source merge')
    graph = json.loads(stage.GRAPH.read_text())
    candidate = next(c for c in transformer_candidates.enumerate_candidates(graph)
                     if c['id'] == tp17.CANDIDATE_ID)
    transcription, parts, l3_r, l3_l = stage.source_parts()
    by_id = {part['source_id']: part for part in transcription['components']}
    parts += [by_id['012-6921:'+name] for name in tp17.SOURCE_PARTS]
    selected, pins = returns.variant_parts(parts, transcription['ports'],
                                           True, 'hv_only_grounded')
    cases = []
    for turns, max_step_ns, flux_probe in CASES:
        variant = copy.deepcopy(parameters)
        variant['groups']['auxiliary'][0]['turns']['value'] = turns
        outcome = returns.run_case(ngspice, graph, variant, candidate,
                                   selected, l3_r, l3_l, max_step_ns,
                                   flux_probe, 90)
        cases.append({'auxiliary_turns': turns, **outcome})
    target = [row for row in cases if row['auxiliary_turns'] == 10.0]
    if len(target) != 3 or any(row['status'] != 'complete' for row in target):
        raise ValueError('10-turn refinement cases did not complete')
    coarse = next(row['result'] for row in target if row['max_step_ns'] == 100
                  and not row['flux_probe_in_deck'])
    fine = next(row['result'] for row in target if row['max_step_ns'] == 50)
    probed = next(row['result'] for row in target if row['flux_probe_in_deck'])
    return {
        'format': 'dac-monitor-t3-ac-loss-candidate-screen-v1',
        'qualification': 'conditional prescribed-drive 4–5 ms stage screen; not a source-validated T3, connected native-grid field, A3 score or A5 freeze',
        'source_hashes': {str(path.relative_to(ROOT)): sha(path) for path in
                          (SOURCE, LOSS, PARAMETERS, stage.GRAPH,
                           returns.RETURN_READ, stage.TRANSCRIPTION, stage.MODELS,
                           ROOT/'magnetics.py', ROOT/'transformer_candidates.py',
                           ROOT/'t3_output_stage_sweep.py',
                           ROOT/'t3_tp17_path_sweep.py',
                           ROOT/'t3_loaded_return_screen.py', Path(__file__).resolve())},
        'ngspice_sha256': sha(ngspice),
        'candidate_id': candidate['id'],
        'equivalent_stage_label': 'T3_PASSIVE_COUPLED_AC_LOSS_HV_COLD_GROUNDED_EQUIVALENT',
        'conditional_return_pins': pins,
        'manual_tp17_guideline_range_vpp': [64, 96],
        'manual_eht_range_v': [11000, 12000],
        'manual_retrace_us': 16,
        'cases': cases,
        'ten_turn_refinement': {
            'tp17_fractional_step_change': abs(fine['sync_swing_v']-coarse['sync_swing_v'])/coarse['sync_swing_v'],
            'eht_fractional_step_change': abs(fine['eht_final_v']-coarse['eht_final_v'])/coarse['eht_final_v'],
            'tp17_fractional_probe_change': abs(probed['sync_swing_v']-coarse['sync_swing_v'])/coarse['sync_swing_v'],
            'one_pulse_per_line_in_window': all(row['result']['flyback_pulse_count'] == 16 for row in target),
            'snapshot_tp17_eht_retrace_in_guideline': all(
                64 <= row['result']['sync_swing_v'] <= 96 and
                11000 <= row['result']['eht_final_v'] <= 12000 and
                12.8 <= row['result']['flyback_width_us_at_10pct_swing_median'] <= 19.2
                for row in target),
        },
        'remaining': ['Source-qualify or bound the return graph and AC-loss model.',
                      'Check joint parameter bounds, collector stress and connected native-grid periodicity before any A5 freeze.'],
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ngspice', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    PARAMETERS.write_text(json.dumps(candidate_parameters(), indent=2)+'\n')
    args.output.write_text(json.dumps(run(args.ngspice), indent=2)+'\n')
