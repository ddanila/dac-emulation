"""Check conditional T3 stage periodicity at the connected-run tolerance.

The prescribed V18 base-drive edge is an exploratory stage input, not a read
of the original driver. No connected or source-validated T3 is claimed.
"""
import argparse
from bisect import bisect_left
import hashlib
import json
import math
from pathlib import Path
import statistics
import subprocess
import tempfile

import t3_ac_loss_candidate_screen as ac
import t3_loaded_return_screen as returns
import t3_output_stage_sweep as stage
import t3_tp17_path_sweep as tp17
import transformer_candidates


ROOT = Path(__file__).resolve().parent
CASES = ((20, 50), (200, 100), (200, 50), (200, 25))
RELTOL = .005
PERIOD_S = 62.5e-6
END_S = .005


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def line_agreement(rows):
    times = [row[0] for row in rows]
    earlier_start = END_S-2*PERIOD_S
    later_start = END_S-PERIOD_S
    phases = sorted(set([0.0, PERIOD_S] +
                        [t-earlier_start for t in times
                         if earlier_start <= t <= later_start] +
                        [t-later_start for t in times
                         if later_start <= t <= END_S]))

    def at(time, column):
        index = bisect_left(times, time)
        if index == 0 or index == len(times):
            raise ValueError('line sample outside trace')
        before, after = rows[index-1], rows[index]
        weight = (time-before[0])/(after[0]-before[0])
        return (1-weight)*before[column]+weight*after[column]

    agreement = {}
    for name, column in [('collector', 1), ('yoke_current', 5),
                         ('core_flux', 7)]:
        earlier = [at(earlier_start+phase, column) for phase in phases]
        later = [at(later_start+phase, column) for phase in phases]
        span = max(earlier)-min(earlier)
        if not math.isfinite(span) or span <= 0:
            raise ValueError('invalid waveform swing')
        agreement[name] = {
            'earlier_swing': span,
            'max_pointwise_difference_fraction_of_swing':
                max(abs(a-b) for a,b in zip(earlier, later))/span,
        }
    return {'period_s': PERIOD_S,
            'line_intervals_s': [[earlier_start, later_start],
                                 [later_start, END_S]],
            'phase_samples': len(phases),
            'phase_selection': 'union of accepted sample phases in both final lines, plus endpoints',
            'waveforms': agreement,
            'all_three_under_0_1_percent': all(
                row['max_pointwise_difference_fraction_of_swing'] <= .001
                for row in agreement.values())}


def run_case(ngspice, graph, parameters, candidate, parts, l3_r, l3_l,
             drive_edge_ns, max_step_ns):
    with tempfile.TemporaryDirectory() as directory:
        trace = Path(directory)/'trace.dat'
        trimmed = Path(directory)/'trace-without-flux.dat'
        circuit = Path(directory)/'stage.cir'
        original, _ = transformer_candidates.compile_model(graph, candidate,
                                                            parameters, backend='flux')
        coupled, _ = transformer_candidates.compile_model(graph, candidate,
                                                           parameters, backend='coupled')
        deck = stage.deck(graph, parameters, candidate, parts, l3_r, l3_l, trace)
        anchors = [(original, coupled),
                   ('.ic v(h_boost)=65',
                    '.param horizontal_brightness_fraction=0.5\n'
                    'Rug1 ug1 0 1G\n.ic v(h_boost)=65'),
                   ('reltol=.001', f'reltol={RELTOL:g}'),
                   ('tran 100n 5m 4m', f'tran {max_step_ns}n 5m 4m'),
                   ('1u 20n 20n 46.5u',
                    f'1u {drive_edge_ns}n {drive_edge_ns}n 46.5u')]
        for old, new in anchors:
            if deck.count(old) != 1:
                raise ValueError('stage deck anchor changed')
            deck = deck.replace(old, new)
        t3 = next(part for part in parts if part['source_id'] == '012-6921:T3')
        flux_vector = f'v({t3["reference"].lower()}.xshared.flux_b)'
        if deck.count('i(Lhorizontal) v(h_boost)') != 1:
            raise ValueError('stage trace anchor changed')
        deck = deck.replace('i(Lhorizontal) v(h_boost)',
                            'i(Lhorizontal) v(h_boost) '+flux_vector)
        circuit.write_text(deck)
        process = subprocess.run([str(ngspice), '-b', str(circuit)],
                                 capture_output=True, text=True, timeout=120)
        if (process.returncode or not trace.is_file() or
                'tran simulation(s) aborted' in process.stdout):
            raise ValueError('T3 stage did not complete')
        with trace.open() as stream:
            header = stream.readline().split()
            records = [line.split() for line in stream if line.strip()]
        expected = ['time', 'v(h_hot)', 'v(eht)', 'v(h_feedback)',
                    'v(h_sync)', 'i(Lhorizontal)', 'v(h_boost)', flux_vector]
        if header != expected:
            raise ValueError('unexpected trace columns')
        rows = [list(map(float, record)) for record in records]
        if len(rows) < 1000 or abs(rows[-1][0]-END_S) > 1e-9:
            raise ValueError('incomplete stage trace')
        trimmed.write_text(' '.join(header[:7])+'\n' +
                           '\n'.join(' '.join(record[:7]) for record in records)+'\n')
        metrics = stage.summarize(trimmed)
        median_step = statistics.median(b[0]-a[0]
                                        for a,b in zip(rows, rows[1:]))
        return {
            'prescribed_base_edge_ns': drive_edge_ns,
            'max_step_ns': max_step_ns,
            'reltol': RELTOL,
            'normalized_deck_sha256': hashlib.sha256(
                deck.replace(str(trace), '<trace>').encode()).hexdigest(),
            'sample_count': len(rows),
            'sample_window_s': [rows[0][0], rows[-1][0]],
            'median_accepted_step_s': median_step,
            'solver_budget_median_at_least_20_ns': median_step >= 20e-9,
            'last_two_lines': line_agreement(rows),
            'stage_metrics': metrics,
            'snapshot_tp17_eht_retrace_in_guideline': (
                64 <= metrics['sync_swing_v'] <= 96 and
                11000 <= metrics['eht_final_v'] <= 12000 and
                metrics['flyback_pulse_count'] == 16 and
                12.8 <= metrics['flyback_width_us_at_10pct_swing_median'] <= 19.2),
        }


def run(ngspice):
    parameters = json.loads(ac.PARAMETERS.read_text())
    if parameters != ac.candidate_parameters():
        raise ValueError('saved conditional parameters changed')
    graph = json.loads(stage.GRAPH.read_text())
    candidate = next(c for c in transformer_candidates.enumerate_candidates(graph)
                     if c['id'] == tp17.CANDIDATE_ID)
    transcription, parts, l3_r, l3_l = stage.source_parts()
    by_id = {part['source_id']: part for part in transcription['components']}
    parts += [by_id['012-6921:'+name] for name in tp17.SOURCE_PARTS]
    selected, pins = returns.variant_parts(parts, transcription['ports'],
                                           True, 'hv_only_grounded')
    cases = [run_case(ngspice, graph, parameters, candidate, selected,
                      l3_r, l3_l, edge, step) for edge,step in CASES]
    nominal = next(row for row in cases if row['prescribed_base_edge_ns'] == 200
                   and row['max_step_ns'] == 50)
    fine = next(row for row in cases if row['prescribed_base_edge_ns'] == 200
                and row['max_step_ns'] == 25)
    changes = {key: abs(fine['stage_metrics'][key]-nominal['stage_metrics'][key]) /
               abs(nominal['stage_metrics'][key])
               for key in ('sync_swing_v', 'eht_final_v', 'collector_peak_v')}
    return {
        'format': 'dac-monitor-t3-stage-refinement-screen-v1',
        'qualification': 'conditional prescribed-drive 4–5 ms stage; not original T3, source-qualified loss, connected field or A5 freeze',
        'source_hashes': {str(path.relative_to(ROOT)): sha(path) for path in
                          (ac.PARAMETERS, ac.SOURCE, ac.LOSS, stage.GRAPH,
                           returns.RETURN_READ, stage.TRANSCRIPTION, stage.MODELS,
                           ROOT/'magnetics.py', ROOT/'transformer_candidates.py',
                           ROOT/'t3_ac_loss_candidate_screen.py',
                           ROOT/'t3_loaded_return_screen.py',
                           ROOT/'t3_output_stage_sweep.py',
                           ROOT/'t3_tp17_path_sweep.py', Path(__file__).resolve())},
        'ngspice_sha256': sha(ngspice),
        'candidate_id': candidate['id'],
        'equivalent_stage_label': 'T3_PASSIVE_COUPLED_AC_LOSS_HV_COLD_GROUNDED_EQUIVALENT',
        'conditional_return_pins': pins,
        'prescribed_drive_edge_basis': '20–200 ns exploratory stage-input sensitivity; a 0.2 us class output-transistor fall-time comparator does not establish the .11 base-drive edge',
        'cases': cases,
        'two_hundred_ns_edge_refinement_fractional_change': changes,
        'two_hundred_ns_edge_both_steps_meet_stage_checks': all(
            row['snapshot_tp17_eht_retrace_in_guideline'] and
            row['last_two_lines']['all_three_under_0_1_percent'] and
            row['solver_budget_median_at_least_20_ns']
            for row in (nominal, fine)),
        'remaining': ['Drive edge is prescribed and not a source-validated V13/T2/L4 waveform.',
                      'Return graph, loss values, other T3 sections, joint bounds and connected periodicity are unqualified.'],
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ngspice', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.write_text(json.dumps(run(args.ngspice), indent=2)+'\n')
