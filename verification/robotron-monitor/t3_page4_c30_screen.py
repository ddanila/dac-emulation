"""Compare C30 population in the corrected, conditional 20-port T3 stage."""

import argparse
from bisect import bisect_left
import hashlib
import json
import math
from pathlib import Path
import subprocess
import tempfile

import page4_t3_visible_wrapper as wrapper
import t3_brimar_boost_boundary_screen as boost
import t3_output_stage_sweep as stage
import t3_page4_visible_stage_screen as visible
import transformer_candidates as tc


ROOT = Path(__file__).resolve().parent
REF = ROOT / 'reference/k7222-11'
OUTPUT = REF / 't3-page4-c30-screen.json'
METRICS = ('eht_at_collector_peak_v', 'yoke_current_pp_a',
           'c21_voltage_at_collector_peak_v')
TP17_NODE = 'h_sync'  # T3 X2:6 and V14 cathode in the source transcription.


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def measure_with_tp17(ngspice, inputs, feed_v, yoke, *, max_step_ns=50):
    """Run the boost bench with its TP17 node retained for a paired comparison."""
    graph, parameters, candidate, parts, l3_r, l3_l = inputs
    with tempfile.TemporaryDirectory() as directory:
        trace = Path(directory) / 'trace.dat'
        circuit = Path(directory) / 'stage.cir'
        deck = stage.deck(graph, parameters, candidate, parts, l3_r, l3_l, trace)
        flux, _ = tc.compile_model(graph, candidate, parameters, backend='flux')
        coupled, _ = tc.compile_model(graph, candidate, parameters, backend='coupled')
        replace = boost.centering.replace_once
        deck = replace(deck, flux, coupled)
        deck = replace(deck, '.ic v(h_boost)=65',
                       '.param horizontal_brightness_fraction=0.5\n'
                       f'Rug1 ug1 0 1G\n.ic v(h_boost)={visible.FEED_V + visible.INITIAL_C21_V:.12g}')
        deck = replace(deck, 'reltol=.001',
                       f'reltol={boost.refinement.RELTOL:g}')
        deck = replace(deck, 'tran 100n 5m 4m',
                       f'tran {max_step_ns}n {visible.STOP_S * 1000:g}m '
                       f'{visible.WINDOW_START_S * 1000:g}m')
        deck = replace(deck, '1u 20n 20n 46.5u', '1u 200n 200n 46.5u')
        deck = replace(deck, 'Rhorizontal hy1 h_winding 2',
                       f'Rhorizontal hy1 h_winding {yoke[1]:.15g}')
        deck = replace(deck, 'Lhorizontal h_winding hy2 4m',
                       f'Lhorizontal h_winding hy2 {yoke[0]:.15g}')
        p = {key: value[0] for key, value in boost.steady_supply.ASSEMBLY_BOUNDS.items()}
        elements = [
            '.param centering_coil_l_h=0.08',
            f".param centering_coil_r_ohm={p['centering_coil_r_ohm']:.15g}",
            f".param centering_r4_a_ohm={p['centering_r4_total_ohm']/2:.15g}",
            f".param centering_r4_b_ohm={p['centering_r4_total_ohm']/2:.15g}",
            f".param centering_r2_ohm={p['centering_r2_ohm']:.15g}",
            boost.bridge.MODEL.read_text(),
            'X971 hy2 centering_a CENTERING_CHOKE',
            'X972 hy1 centering_w CENTERING_CHOKE',
            'X973 centering_a centering_b centering_w CENTERING_POT',
            'R974 centering_b centering_c {centering_r2_ohm}',
            'Vp12 p12 0 DC 12',
            'Rlink0 centering_a 0 1m',
            'Rlink1 centering_c p12 1m',
        ]
        deck = replace(deck, 'Rhy2ref hy2 0 1G',
                       'Rhy2ref hy2 0 1G\n' + '\n'.join(elements))
        deck = replace(deck, 'Vfeed h_feed 0 41',
                       f'Vfeed h_feed 0 {feed_v:.12g}')
        deck = replace(deck,
                       f'wrdata {trace} v(h_hot) v(eht) v(h_feedback) '
                       'v(h_sync) i(Lhorizontal) v(h_boost)',
                       f'wrdata {trace} v(h_hot) v(h_return) '
                       'v(h_hot,h_return) v(hy2) v(eht) '
                       'i(Lhorizontal) v(h_boost) '
                       'v(h_boost,h_feed) v(h_sync)')
        digest = hashlib.sha256(deck.replace(str(trace), '<trace>').encode()).hexdigest()
        circuit.write_text(deck)
        result = subprocess.run([str(ngspice), '-b', str(circuit)],
                                capture_output=True, text=True, timeout=180)
        if result.returncode or not trace.is_file() or 'tran simulation(s) aborted' in result.stdout:
            raise ValueError('conditional C30/TP17 stage failed: ' +
                             '\n'.join((result.stdout + result.stderr).splitlines()[-15:]))
        with trace.open() as stream:
            header = stream.readline().split()
            rows = [list(map(float, line.split())) for line in stream if line.strip()]
    expected = ['time', 'v(h_hot)', 'v(h_return)', 'v(h_hot,h_return)',
                'v(hy2)', 'v(eht)', 'i(Lhorizontal)', 'v(h_boost)',
                'v(h_boost,h_feed)', f'v({TP17_NODE})']
    if header != expected or not rows or abs(rows[-1][0] - visible.STOP_S) > 1e-9:
        raise ValueError('incomplete C30/TP17 trace')
    last = [row for row in rows if row[0] >= visible.STOP_S - .000125]
    if len(last) < 1000 or any(len(row) != 10 or not all(map(math.isfinite, row))
                               for row in last):
        raise ValueError('invalid final two-line C30/TP17 trace')
    collector = max(last, key=lambda row: row[1])
    tp17_values = [row[9] for row in last]
    observed = dict(normalized_deck_sha256=digest, sample_count=len(last),
                    yoke_current_pp_a=max(row[6] for row in last)-min(row[6] for row in last),
                    eht_at_collector_peak_v=collector[5],
                    boost_node_at_collector_peak_v=collector[7],
                    boost_node_range_v=[min(row[7] for row in last), max(row[7] for row in last)],
                    c21_voltage_at_collector_peak_v=collector[8],
                    c21_voltage_range_v=[min(row[8] for row in last), max(row[8] for row in last)],
                    c21_window_phase_drift_v=rows[-1][8]-rows[0][8],
                    eht_window_phase_drift_v=rows[-1][5]-rows[0][5],
                    tp17_min_v=min(tp17_values), tp17_max_v=max(tp17_values),
                    tp17_pp_v=max(tp17_values)-min(tp17_values))
    return observed, [(row[0], row[9]) for row in last]


def sample_waveform(waveform, times):
    xs = [point[0] for point in waveform]
    result = []
    for instant in times:
        right = bisect_left(xs, instant)
        if right == 0 or right == len(xs):
            raise ValueError('TP17 comparison grid outside saved trace')
        left = right - 1
        fraction = (instant - xs[left]) / (xs[right] - xs[left])
        result.append(waveform[left][1] + fraction *
                      (waveform[right][1] - waveform[left][1]))
    return result


def compare_tp17(cases, waveforms, grid_step_ns):
    step = grid_step_ns * 1e-9
    grid_start = max(waveform[0][0] for waveform in waveforms)
    grid_end = min(waveform[-1][0] for waveform in waveforms)
    grid = [grid_start + (i + 1) * step
            for i in range(int((grid_end - grid_start) / step) - 1)]
    if len(grid) < 2000:
        raise ValueError('too few common TP17 comparison samples')
    populated, absent = [sample_waveform(waveform, grid) for waveform in waveforms]
    differences = [a - p for p, a in zip(populated, absent)]
    tp17_pp = cases[0]['observed']['tp17_pp_v']
    if tp17_pp <= 0:
        raise ValueError('TP17 baseline has no pulse')
    largest_index = max(range(len(differences)), key=lambda i: abs(differences[i]))
    return dict(node=TP17_NODE, grid_step_ns=grid_step_ns,
                grid_sample_count=len(grid), grid_window_s=[grid[0], grid[-1]],
                peak_difference_time_s=grid[largest_index],
                peak_signed_difference_v=differences[largest_index],
                peak_absolute_difference_v=abs(differences[largest_index]),
                peak_difference_over_populated_pp=abs(differences[largest_index]) / tp17_pp,
                rms_difference_over_populated_pp=(
                    sum(value * value for value in differences) / len(differences)) ** .5 / tp17_pp,
                pp_relative_to_populated=(cases[1]['observed']['tp17_pp_v'] - tp17_pp) / tp17_pp)


def run(ngspice, source_pdf):
    prior = json.loads(visible.OUTPUT.read_text())
    if prior['format'] != 'dac-monitor-t3-page4-visible-stage-screen-v1':
        raise ValueError('corrected 20-port screen changed')
    for name, digest in prior['input_sha256'].items():
        if sha(ROOT / name) != digest:
            raise ValueError(f'corrected 20-port screen input stale: {name}')
    if sha(source_pdf) != prior['source_pdf_sha256'] or sha(ngspice) != prior['ngspice_sha256']:
        raise ValueError('source or solver differs from corrected stage screen')
    checked = wrapper.run(source_pdf)
    if checked != json.loads(wrapper.OUTPUT.read_text()) or not checked['passed']:
        raise ValueError('20-port KiCad/source interface changed')
    graph = json.loads(visible.GRAPH.read_text())
    parameters = visible.transferred_parameters(json.loads(visible.BASE_PARAMETERS.read_text()))
    transcription, parts, l3_r, l3_l = visible.prepared_parts(
        graph, checked['exported_nodes'])
    c30 = [part for part in parts if part['source_id'] == '012-6921:C30']
    if len(c30) != 1 or set(c30[0]['nodes']) != {'h_hot', '0'}:
        raise ValueError('C30 model placement changed')
    catalog = json.loads(boost.rail.CATALOG.read_text())
    yoke_row = next(row for row in catalog['class_cases'] if row['type'] == 'TBY7')
    yoke = (yoke_row['line_inductance_h'], yoke_row['line_resistance_ohm'])
    polarity = {'drive': 1, 'auxiliary': 1, 'high_voltage': 1, 'lower_taps': 1}
    candidate = next(row for row in tc.enumerate_candidates(graph)
                     if row['polarity'] == polarity)
    baseline = next(row for row in prior['cases'] if row['relative_polarity'] == polarity)
    if baseline['status'] != 'complete':
        raise ValueError('corrected 20-port baseline did not complete')
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / 'page4-visible-transcription.json'
        path.write_text(json.dumps(transcription, indent=2) + '\n')
        saved = stage.TRANSCRIPTION
        try:
            stage.TRANSCRIPTION = path
            screens = {}
            for max_step_ns in (50, 25):
                cases = []
                waveforms = []
                for populated in (True, False):
                    selected = (parts if populated else
                                [part for part in parts if part['source_id'] != '012-6921:C30'])
                    print(f"screening C30 {'populated' if populated else 'absent'} "
                          f'at {max_step_ns} ns', flush=True)
                    observed, waveform = measure_with_tp17(
                        ngspice, (graph, parameters, candidate, selected, l3_r, l3_l),
                        visible.FEED_V, yoke, max_step_ns=max_step_ns)
                    cases.append(dict(c30_populated=populated, observed=observed))
                    waveforms.append(waveform)
                screens[max_step_ns] = (cases, compare_tp17(cases, waveforms, max_step_ns))
        finally:
            stage.TRANSCRIPTION = saved
    cases, tp17_comparison = screens[50]
    refined_cases, refined_tp17_comparison = screens[25]
    for metric, tolerance in (('eht_at_collector_peak_v', .02),
                              ('yoke_current_pp_a', 2e-6),
                              ('c21_voltage_at_collector_peak_v', .002)):
        if abs(cases[0]['observed'][metric] - baseline['observed'][metric]) > tolerance:
            raise ValueError(f'corrected C30 baseline differs: {metric}')
    relative = {metric: (cases[1]['observed'][metric] - cases[0]['observed'][metric])
                / cases[0]['observed'][metric] for metric in METRICS}
    dependencies = (visible.OUTPUT, visible.GRAPH, visible.BASE_PARAMETERS,
                    wrapper.OUTPUT, wrapper.CANDIDATE_SHEET, stage.TRANSCRIPTION,
                    stage.MODELS, stage.PROFILE, boost.rail.CATALOG,
                    boost.bridge.MODEL, ROOT / 'magnetics.py',
                    ROOT / 'transformer_candidates.py',
                    ROOT / 'page4_t3_visible_wrapper.py',
                    ROOT / 't3_page4_visible_stage_screen.py',
                    ROOT / 't3_brimar_boost_boundary_screen.py',
                    ROOT / 't3_output_stage_sweep.py', Path(__file__))
    return dict(format='dac-monitor-t3-page4-c30-screen-v2',
                qualification='paired 20 ms prescribed-drive C30 population sensitivity in one provisional source-visible 20-port T3 graph; does not identify installed C30 or qualify periodic operation',
                input_sha256={str(path.relative_to(ROOT)): sha(path)
                              for path in dependencies},
                source_pdf_sha256=sha(source_pdf), ngspice_sha256=sha(ngspice),
                conditions=prior['conditions'], relative_polarity=polarity,
                cases=cases, absent_relative_to_populated=relative,
                tp17_waveform_comparison=tp17_comparison,
                refined_step_ns=25,
                refined_cases=refined_cases,
                refined_tp17_waveform_comparison=refined_tp17_comparison,
                sampled_three_metric_within_2pct=all(abs(value) <= .02 for value in relative.values()),
                sampled_tp17_waveform_within_2pct=all(
                    comparison['peak_difference_over_populated_pp'] <= .02
                    for comparison in (tp17_comparison, refined_tp17_comparison)),
                limitations=['Only a provisional prescribed-drive TP17 pulse is compared; connected native drive and periodic operation are not checked.',
                             'C30 source placement and installed population remain unverified; the T3 graph and winding parameters are provisional.'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ngspice', type=Path, required=True)
    parser.add_argument('--source-pdf', type=Path, default=visible.SOURCE_PDF)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args()
    report = run(args.ngspice, args.source_pdf)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(report['absent_relative_to_populated'])
