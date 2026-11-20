"""Reproduce a conditional AC-loss T3 candidate on the loaded TP17 stage.

This prescribed-drive 4–5 ms screen does not qualify the original T3 graph or
a sustained connected monitor. It records a labelled fallback candidate.
"""
import argparse
from bisect import bisect_left
import copy
import hashlib
import json
import math
from pathlib import Path
import statistics
import subprocess
import tempfile

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


def periodicity_case(ngspice, graph, parameters, candidate, parts, l3_r, l3_l):
    """Compare consecutive final drive periods, including internal core flux."""
    with tempfile.TemporaryDirectory() as directory:
        trace = Path(directory)/'trace.dat'
        circuit = Path(directory)/'stage.cir'
        original, _ = transformer_candidates.compile_model(graph, candidate,
                                                            parameters, backend='flux')
        coupled, _ = transformer_candidates.compile_model(graph, candidate,
                                                           parameters, backend='coupled')
        deck = stage.deck(graph, parameters, candidate, parts, l3_r, l3_l, trace)
        if deck.count(original) != 1:
            raise ValueError('stage magnetic model changed')
        deck = deck.replace(original, coupled)
        if deck.count('.ic v(h_boost)=65') != 1:
            raise ValueError('stage initial-condition anchor changed')
        deck = deck.replace('.ic v(h_boost)=65',
                            '.param horizontal_brightness_fraction=0.5\n'
                            'Rug1 ug1 0 1G\n.ic v(h_boost)=65')
        t3 = next(part for part in parts if part['source_id'] == '012-6921:T3')
        flux_vector = f'v({t3["reference"].lower()}.xshared.flux_b)'
        anchor = 'i(Lhorizontal) v(h_boost)'
        if deck.count(anchor) != 1:
            raise ValueError('stage trace anchor changed')
        deck = deck.replace(anchor, anchor+' '+flux_vector)
        circuit.write_text(deck)
        process = subprocess.run([str(ngspice), '-b', str(circuit)],
                                 capture_output=True, text=True, timeout=90)
        if process.returncode or not trace.is_file() or 'tran simulation(s) aborted' in process.stdout:
            raise ValueError('flux-probe periodicity run did not complete')
        with trace.open() as stream:
            columns = stream.readline().split()
            rows = [list(map(float, line.split())) for line in stream if line.strip()]
        if columns != ['time', 'v(h_hot)', 'v(eht)', 'v(h_feedback)',
                       'v(h_sync)', 'i(Lhorizontal)', 'v(h_boost)', flux_vector]:
            raise ValueError('unexpected periodicity trace columns')
        times = [row[0] for row in rows]
        if len(rows) < 1000 or abs(times[-1]-.005) > 1e-9:
            raise ValueError('incomplete periodicity trace')

        def at(time, column):
            index = bisect_left(times, time)
            if index == 0 or index == len(times):
                raise ValueError('periodicity sample outside trace')
            before, after = rows[index-1], rows[index]
            weight = (time-before[0])/(after[0]-before[0])
            return (1-weight)*before[column]+weight*after[column]

        period = 62.5e-6
        first_start = .005-2*period
        second_start = .005-period
        # Use every accepted phase from both lines. A fixed 100 ns grid misses
        # a narrow collector difference near one flyback edge.
        phases = sorted(set([0.0, period] +
                            [time-first_start for time in times
                             if first_start <= time <= second_start] +
                            [time-second_start for time in times
                             if second_start <= time <= .005]))
        agreement = {}
        for name, column in [('collector', 1), ('yoke_current', 5),
                             ('core_flux', 7)]:
            earlier = [at(first_start+phase, column) for phase in phases]
            later = [at(second_start+phase, column) for phase in phases]
            span = max(earlier)-min(earlier)
            if not math.isfinite(span) or span <= 0:
                raise ValueError('invalid periodicity waveform span')
            agreement[name] = {
                'earlier_swing': span,
                'max_pointwise_difference_fraction_of_swing':
                    max(abs(a-b) for a,b in zip(earlier, later))/span,
            }
        median_step = statistics.median(b-a for a,b in zip(times, times[1:]))
        return {
            'normalized_deck_sha256': hashlib.sha256(
                deck.replace(str(trace), '<trace>').encode()).hexdigest(),
            'sample_count': len(rows),
            'window_s': [times[0], times[-1]],
            'line_period_s': period,
            'compared_line_intervals_s': [[first_start, second_start],
                                          [second_start, .005]],
            'phase_samples': len(phases),
            'phase_selection': 'union of accepted sample phases in both final lines, plus endpoints',
            'waveform_agreement': agreement,
            'all_three_under_0_1_percent': all(
                row['max_pointwise_difference_fraction_of_swing'] <= .001
                for row in agreement.values()),
            'median_accepted_step_s': median_step,
            'solver_budget_median_at_least_20_ns': median_step >= 20e-9,
        }


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
        'last_two_line_periodicity': periodicity_case(
            ngspice, graph, parameters, candidate, selected, l3_r, l3_l),
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
                      'Improve the sub-20-ns median solver step before a connected run.',
                      'Check joint parameter bounds, collector stress and connected native-grid periodicity before any A5 freeze.'],
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ngspice', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    PARAMETERS.write_text(json.dumps(candidate_parameters(), indent=2)+'\n')
    args.output.write_text(json.dumps(run(args.ngspice), indent=2)+'\n')
