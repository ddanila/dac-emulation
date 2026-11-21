"""Compare C30 population in the corrected, conditional 20-port T3 stage."""

import argparse
import hashlib
import json
from pathlib import Path
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


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


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
            cases = []
            for populated in (True, False):
                selected = (parts if populated else
                            [part for part in parts if part['source_id'] != '012-6921:C30'])
                print(f"screening C30 {'populated' if populated else 'absent'}", flush=True)
                observed = boost.measure(
                    ngspice, (graph, parameters, candidate, selected, l3_r, l3_l, {}),
                    visible.FEED_V, yoke,
                    initial_boost_node_v=visible.FEED_V + visible.INITIAL_C21_V,
                    stop_s=visible.STOP_S, window_start_s=visible.WINDOW_START_S)
                cases.append(dict(c30_populated=populated, observed=observed))
        finally:
            stage.TRANSCRIPTION = saved
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
    return dict(format='dac-monitor-t3-page4-c30-screen-v1',
                qualification='paired 20 ms prescribed-drive C30 population sensitivity in one provisional source-visible 20-port T3 graph; does not identify installed C30 or qualify periodic operation',
                input_sha256={str(path.relative_to(ROOT)): sha(path)
                              for path in dependencies},
                source_pdf_sha256=sha(source_pdf), ngspice_sha256=sha(ngspice),
                conditions=prior['conditions'], relative_polarity=polarity,
                cases=cases, absent_relative_to_populated=relative,
                sampled_three_metric_within_2pct=all(abs(value) <= .02 for value in relative.values()),
                limitations=['Only EHT, horizontal yoke current and C21 are compared; TP17 pulse shape and connected native drive are not checked.',
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
