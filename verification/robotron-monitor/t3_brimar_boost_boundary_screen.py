"""Probe C21 boost in the six conditional T3 return cases at the TBY7 boundary."""

import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import subprocess
import tempfile

import centering_bridge_check as bridge
import steady_supply
import t3_brimar_rail_boundary_screen as rail
import t3_brimar_return_boundary_screen as returns_screen
import t3_centering_return_screen as centering
import t3_drive_pulse_screen as pulse
import t3_loaded_return_screen as returns
import t3_output_stage_sweep as stage
import t3_stage_refinement_screen as refinement
import t3_tp17_path_sweep as tp17
import transformer_candidates


ROOT = Path(__file__).resolve().parent
REF = ROOT / 'reference/k7222-11'
OUTPUT = REF / 't3-brimar-boost-boundary-screen.json'
LATER_SOURCE = REF / 'k7222-25-horizontal-source-read.json'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def measure(ngspice, inputs, feed_v, yoke):
    """Use the centring screen's stage substitutions, adding only a boost probe."""
    graph, parameters, candidate, parts, l3_r, l3_l, _ = inputs
    with tempfile.TemporaryDirectory() as directory:
        trace = Path(directory) / 'trace.dat'
        circuit = Path(directory) / 'stage.cir'
        deck = stage.deck(graph, parameters, candidate, parts, l3_r, l3_l, trace)
        flux, _ = transformer_candidates.compile_model(graph, candidate, parameters,
                                                        backend='flux')
        coupled, _ = transformer_candidates.compile_model(graph, candidate, parameters,
                                                           backend='coupled')
        deck = centering.replace_once(deck, flux, coupled)
        deck = centering.replace_once(deck, '.ic v(h_boost)=65',
                                      '.param horizontal_brightness_fraction=0.5\n'
                                      'Rug1 ug1 0 1G\n.ic v(h_boost)=65')
        deck = centering.replace_once(deck, 'reltol=.001',
                                      f'reltol={refinement.RELTOL:g}')
        deck = centering.replace_once(deck, 'tran 100n 5m 4m', 'tran 50n 5m 4m')
        deck = centering.replace_once(deck, '1u 20n 20n 46.5u',
                                      '1u 200n 200n 46.5u')
        deck = centering.replace_once(deck, 'Rhorizontal hy1 h_winding 2',
                                      f'Rhorizontal hy1 h_winding {yoke[1]:.15g}')
        deck = centering.replace_once(deck, 'Lhorizontal h_winding hy2 4m',
                                      f'Lhorizontal h_winding hy2 {yoke[0]:.15g}')
        p = {key: value[0] for key, value in steady_supply.ASSEMBLY_BOUNDS.items()}
        elements = [
            '.param centering_coil_l_h=0.08',
            f".param centering_coil_r_ohm={p['centering_coil_r_ohm']:.15g}",
            f".param centering_r4_a_ohm={p['centering_r4_total_ohm']/2:.15g}",
            f".param centering_r4_b_ohm={p['centering_r4_total_ohm']/2:.15g}",
            f".param centering_r2_ohm={p['centering_r2_ohm']:.15g}",
            bridge.MODEL.read_text(),
            'X971 hy2 centering_a CENTERING_CHOKE',
            'X972 hy1 centering_w CENTERING_CHOKE',
            'X973 centering_a centering_b centering_w CENTERING_POT',
            'R974 centering_b centering_c {centering_r2_ohm}',
            'Vp12 p12 0 DC 12',
            'Rlink0 centering_a 0 1m',
            'Rlink1 centering_c p12 1m',
        ]
        deck = centering.replace_once(deck, 'Rhy2ref hy2 0 1G',
                                      'Rhy2ref hy2 0 1G\n' + '\n'.join(elements))
        deck = centering.replace_once(deck, 'Vfeed h_feed 0 41',
                                      f'Vfeed h_feed 0 {feed_v:.12g}')
        deck = centering.replace_once(deck,
                                      f'wrdata {trace} v(h_hot) v(eht) v(h_feedback) '
                                      'v(h_sync) i(Lhorizontal) v(h_boost)',
                                      f'wrdata {trace} v(h_hot) v(h_return) '
                                      'v(h_hot,h_return) v(hy2) v(eht) '
                                      'i(Lhorizontal) v(h_boost) '
                                      'v(h_boost,h_feed)')
        digest = hashlib.sha256(deck.replace(str(trace), '<trace>').encode()).hexdigest()
        circuit.write_text(deck)
        process = subprocess.run([str(ngspice), '-b', str(circuit)],
                                 capture_output=True, text=True, timeout=180)
        if process.returncode or not trace.is_file() or 'tran simulation(s) aborted' in process.stdout:
            raise ValueError('conditional boost stage failed: ' +
                             '\n'.join((process.stdout + process.stderr).splitlines()[-15:]))
        with trace.open() as stream:
            header = stream.readline().split()
            rows = [list(map(float, line.split())) for line in stream if line.strip()]
    expected = ['time', 'v(h_hot)', 'v(h_return)', 'v(h_hot,h_return)',
                'v(hy2)', 'v(eht)', 'i(Lhorizontal)', 'v(h_boost)',
                'v(h_boost,h_feed)']
    if header != expected or not rows or abs(rows[-1][0] - pulse.END_S) > 1e-9:
        raise ValueError('incomplete boost trace')
    last = [row for row in rows if row[0] >= pulse.WINDOW_START_S]
    if len(last) < 1000 or any(len(row) != 9 or not all(map(math.isfinite, row))
                               for row in last):
        raise ValueError('invalid final two-line boost trace')
    collector = max(last, key=lambda row: row[1])
    return dict(normalized_deck_sha256=digest, sample_count=len(last),
                yoke_current_pp_a=max(row[6] for row in last)-min(row[6] for row in last),
                eht_at_collector_peak_v=collector[5],
                boost_node_at_collector_peak_v=collector[7],
                boost_node_range_v=[min(row[7] for row in last),
                                    max(row[7] for row in last)],
                c21_voltage_at_collector_peak_v=collector[8],
                c21_voltage_range_v=[min(row[8] for row in last),
                                     max(row[8] for row in last)])


def run(ngspice, source_pdf, later_pdf):
    if sha(source_pdf) != rail.SOURCE_PDF_SHA:
        raise ValueError('K7222.11 source scan changed')
    later = json.loads(LATER_SOURCE.read_text())
    if sha(later_pdf) != later['source']['local_pdf_sha256']:
        raise ValueError('K7222.25 source scan changed')
    boost_bounds = later['horizontal_stage_k7222_25']['boost_at_c21_v']
    if not later['horizontal_stage_k7222_25']['boost_voltage_reference'].startswith('across C21'):
        raise ValueError('K7222.25 boost voltage reference changed')
    # The K7222.11 page-4 handwritten "Booster-C C21 60..70 V" agrees with
    # the later manual's across-capacitor statement, not a node-to-ground value.
    if boost_bounds != [60, 70]:
        raise ValueError('cross-revision C21 comparator changed')
    prior = json.loads(returns_screen.OUTPUT.read_text())
    crossing = prior['prior_boundary_feed_v']
    catalog = json.loads(rail.CATALOG.read_text())
    tby7 = next(row for row in catalog['class_cases'] if row['type'] == 'TBY7')
    yoke = (tby7['line_inductance_h'], tby7['line_resistance_ohm'])
    inputs = pulse.setup()
    transcription, parts, _, _ = stage.source_parts()
    by_id = {part['source_id']: part for part in transcription['components']}
    if by_id['012-6921:C21']['nodes'] != ['h_feed', 'h_boost']:
        raise ValueError('C21 terminal map changed; review differential probe')
    parts += [by_id['012-6921:' + name] for name in tp17.SOURCE_PARTS]
    rows = []
    for joined in (True, False):
        for mode in ('shared_floating', 'hv_only_grounded', 'shared_grounded'):
            if mode == 'shared_floating':
                selected = copy.deepcopy(parts)
                t3 = next(part for part in selected if part['source_id'] == '012-6921:T3')
                nodes = dict(zip(transcription['ports'], t3['nodes']))
                if not joined:
                    nodes['X1_3'] = 'h_upper_return'
                t3['nodes'] = [nodes[port] for port in transcription['ports']]
            else:
                selected, _ = returns.variant_parts(parts, transcription['ports'],
                                                    joined, mode)
            observed = measure(ngspice, (*inputs[:3], selected, *inputs[4:6], {}),
                               crossing, yoke)
            baseline = next(row for row in prior['cases']
                            if row['upper_return_tied'] == joined and
                            row['cold_mode'] == mode and row['feed_v'] == crossing)
            for key, tolerance in (('yoke_current_pp_a', 2e-6),
                                   ('eht_at_collector_peak_v', .02)):
                if abs(observed[key]-baseline[key]) > tolerance:
                    raise ValueError(f'boost probe changed {key} for {joined}/{mode}')
            c21_matches = (boost_bounds[0] <= observed['c21_voltage_at_collector_peak_v']
                           <= boost_bounds[1])
            current_eht_match = (baseline['reaches_class_lower_current'] and
                                 baseline['sampled_eht_in_manual_band'])
            rows.append(dict(upper_return_tied=joined, cold_mode=mode,
                             **observed,
                             prior_current_and_eht_match=current_eht_match,
                             within_source_annotated_c21_voltage_band=c21_matches,
                             current_eht_and_c21_match=current_eht_match and c21_matches))
    return dict(format='dac-monitor-t3-brimar-boost-boundary-screen-v1',
                qualification='conditional K7222.11 T3/Brimar TBY7 prescribed-base stage; page-4 handwritten C21 annotation is a source check, while K7222.25 AE9VT description is cross-revision corroboration; neither is a periodic installed-state score',
                source=dict(k7222_11_pdf_sha256=sha(source_pdf),
                            k7222_11_c21_annotation_pdf_page=4,
                            k7222_25_pdf_sha256=sha(later_pdf)),
                input_sha256={str(path.relative_to(ROOT)): sha(path) for path in
                              (LATER_SOURCE, returns_screen.OUTPUT, rail.CATALOG,
                               stage.GRAPH, stage.PARAMETERS, stage.TRANSCRIPTION,
                               stage.MODELS, bridge.MODEL,
                               ROOT / 'steady_supply.py',
                               ROOT / 'transformer_candidates.py',
                               ROOT / 't3_brimar_rail_boundary_screen.py',
                               ROOT / 't3_brimar_return_boundary_screen.py',
                               ROOT / 't3_centering_return_screen.py',
                               ROOT / 't3_drive_pulse_screen.py',
                               ROOT / 't3_stage_refinement_screen.py',
                               ROOT / 't3_output_stage_sweep.py',
                               ROOT / 't3_loaded_return_screen.py',
                               ROOT / 't3_tp17_path_sweep.py', Path(__file__))},
                ngspice_sha256=sha(ngspice),
                fixed_conditions=dict(feed_v=crossing, yoke='TBY7',
                                      centering_link_pair='E1+E2',
                                      centering_coil_l_h=.08, max_step_ns=50,
                                      initial_boost_node_v=65,
                                      initial_c21_differential_v=65-crossing),
                source_annotated_c21_voltage_v=boost_bounds,
                later_ae9vt_c21_corrob_v=boost_bounds,
                cases=rows,
                joint_matches=sum(row['current_eht_and_c21_match'] for row in rows),
                interpretation='The .11 page-4 annotation and later AE9VT manual refer to voltage across C21. The four return wirings that previously met sampled current and EHT give only about 23.67–23.70 V across C21 at the collector peak, despite about 66.2 V at the boost node relative to ground. None of the six conditional cases meets all three sampled checks. The deck initializes the 220 uF C21 boost node at 65 V and runs only 5 ms, so this is not a settled booster measurement and cannot reject a physical return graph. The active stage cannot yet be called document-consistent; the result does not identify the winding graph or supply a T3 ratio.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ngspice', type=Path, required=True)
    parser.add_argument('--source-pdf', type=Path, required=True)
    parser.add_argument('--later-pdf', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args()
    report = run(args.ngspice, args.source_pdf, args.later_pdf)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print([(row['upper_return_tied'], row['cold_mode'], row['c21_voltage_at_collector_peak_v'])
           for row in report['cases']])
