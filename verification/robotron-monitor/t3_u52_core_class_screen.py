"""Compare a later Robotron U52/54 core statement with an independent U52 class."""

import argparse
import copy
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import t3_brimar_rail_boundary_screen as rail
import t3_drive_pulse_screen as pulse


ROOT = Path(__file__).resolve().parent
REF = ROOT / 'reference/k7222-11'
SOURCE = REF / 't3-u52-core-source-read.json'
OUTPUT = REF / 't3-u52-core-class-screen.json'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def half_step(ngspice, inputs, feed, yoke):
    original = rail.centering.replace_once

    def refine(deck, old, new):
        if old == 'tran 100n 5m 4m' and new == 'tran 50n 5m 4m':
            new = 'tran 25n 5m 4m'
        return original(deck, old, new)

    with patch.object(rail.centering, 'replace_once', refine):
        return rail.rail_case(ngspice, inputs, feed, yoke)


def run(ngspice, robotron_pdf, fonox_pdf):
    source = json.loads(SOURCE.read_text())
    if sha(robotron_pdf) != source['robotron']['sha256']:
        raise ValueError('cross-revision Robotron source changed')
    if sha(fonox_pdf) != source['fonox']['sha256']:
        raise ValueError('U52 class catalog changed')
    catalog = json.loads(rail.CATALOG.read_text())
    boundary = json.loads(rail.BOUNDARY.read_text())
    prior = json.loads(rail.OUTPUT.read_text())
    tby7 = next(row for row in catalog['class_cases'] if row['type'] == 'TBY7')
    yoke = (tby7['line_inductance_h'], tby7['line_resistance_ohm'])
    lower = boundary['axes']['horizontal']['current_pp_a']['bounds'][0]
    eht = prior['manual_eht_bounds_v']
    crossing = prior['threshold']['first_within']['feed_v']
    base = pulse.setup()
    active_core = base[1]['core']
    area = source['fonox']['effective_area_mm2'] * 1e-6
    length = source['fonox']['effective_path_length_mm'] * 1e-3
    geometries = [
        ('active_model', active_core['area_m2']['value'], active_core['length_m']['value']),
        ('U52_area_only', area, active_core['length_m']['value']),
        ('U52_area_and_length', area, length),
    ]
    h, b = active_core['h_a_per_m'], active_core['b_t']
    middle = h.index(0)
    slope = (b[middle+1] - b[middle]) / (h[middle+1] - h[middle])
    rows = []
    for label, area_m2, length_m in geometries:
        inputs = list(base)
        inputs[1] = copy.deepcopy(base[1])
        inputs[1]['core']['area_m2']['value'] = area_m2
        inputs[1]['core']['length_m']['value'] = length_m
        feeds = (crossing,) if label == 'active_model' else (41., crossing, 43.)
        cases = []
        for feed in feeds:
            observed = rail.rail_case(ngspice, tuple(inputs), feed, yoke)
            cases.append(dict(feed_v=feed,
                              yoke_current_pp_a=observed['yoke_current_pp_a'],
                              eht_at_collector_peak_v=observed['eht_at_collector_peak_v'],
                              drive_peak_v=observed['drive_peak_v'],
                              current_in_transferred_class=observed['yoke_current_pp_a'] >= lower,
                              sampled_eht_in_manual_band=eht[0] <= observed['eht_at_collector_peak_v'] <= eht[1],
                              normalized_deck_sha256=observed['normalized_deck_sha256']))
        if label != 'active_model':
            refined = half_step(ngspice, tuple(inputs), crossing, yoke)
            cases.append(dict(feed_v=crossing, max_step_ns=25,
                              yoke_current_pp_a=refined['yoke_current_pp_a'],
                              eht_at_collector_peak_v=refined['eht_at_collector_peak_v'],
                              drive_peak_v=refined['drive_peak_v'],
                              current_in_transferred_class=refined['yoke_current_pp_a'] >= lower,
                              sampled_eht_in_manual_band=eht[0] <= refined['eht_at_collector_peak_v'] <= eht[1],
                              normalized_deck_sha256=refined['normalized_deck_sha256']))
        rows.append(dict(geometry=label, effective_area_m2=area_m2,
                         effective_path_length_m=length_m,
                         retained_provisional_bh_origin_slope_t_per_a_per_m=slope,
                         implied_model_al_nh_per_turn2=area_m2/length_m*slope*1e9,
                         cases=cases))
    old = prior['threshold']['first_within']
    baseline = rows[0]['cases'][0]
    if (abs(baseline['yoke_current_pp_a']-old['yoke_current_pp_a']) > 1e-6 or
            abs(baseline['eht_at_collector_peak_v']-old['eht_at_collector_peak_v']) > .01):
        raise ValueError('active-core case differs from saved TBY7 rail crossing')
    al = source['fonox']['al_nh_per_turn2']
    turns = base[1]['groups']['drive'][0]['turns']['value']
    loss = source['fonox']['loss_reference']
    vrms = 4.442882938 * loss['frequency_hz'] * turns * area * loss['flux_amplitude_t']
    return dict(
        format='dac-monitor-t3-u52-core-class-screen-v1',
        qualification='cross-revision U52/54 and independent U52/H21 class geometry; area/path-only 4–5 ms prescribed-drive sensitivity with provisional B-H curve, T3 graph and TBY7 yoke, not a .11 core identification or A5 freeze',
        source_read_sha256=sha(SOURCE),
        source_pdf_sha256=dict(robotron=sha(robotron_pdf), fonox=sha(fonox_pdf)),
        input_sha256={str(path.relative_to(ROOT)): sha(path) for path in
                      (rail.OUTPUT, rail.BOUNDARY, rail.CATALOG, pulse.ac.PARAMETERS,
                       rail.centering.bridge.MODEL, rail.centering.stage.GRAPH,
                       rail.centering.stage.TRANSCRIPTION, rail.centering.stage.MODELS,
                       ROOT/'steady_supply.py', ROOT/'transformer_candidates.py',
                       ROOT/'magnetics.py', ROOT/'t3_brimar_rail_boundary_screen.py',
                       ROOT/'t3_centering_return_screen.py',
                       ROOT/'t3_drive_pulse_screen.py', Path(__file__))},
        ngspice_sha256=sha(ngspice),
        fixed_conditions=dict(yoke_type='TBY7', yoke_line_l_h=yoke[0],
                              yoke_line_r_ohm=yoke[1], centering_link_pair='E1+E2',
                              centering_coil_l_h=.08, prescribed_base_edge_ns=200,
                              nominal_max_step_ns=50, refined_max_step_ns=25,
                              provisional_bh_and_loss_unchanged=True),
        class_lower_current_pp_a=lower, manual_eht_bounds_v=eht,
        prior_boundary_feed_v=crossing,
        catalog_al_nh_per_turn2=dict(nominal=al,
                                     tolerance_bounds=[al*(1-source['fonox']['al_tolerance_fraction']),
                                                       al*(1+source['fonox']['al_tolerance_fraction'])],
                                     scope='FONOX U52/H21 set with no intentional gap specified; not transferable to an unmeasured flyback gap'),
        catalog_loss_reference=dict(first_drive_section_turns=turns,
                                    sine_voltage_rms_v=vrms,
                                    catalog_maximum_w=loss['maximum_w'],
                                    equivalent_shunt_minimum_ohm_at_reference=vrms**2/loss['maximum_w'],
                                    active_shunt_ohm=active_core['loss_ohm']['value'],
                                    scope='15 kHz, 200 mT sine, 100 C catalog maximum only; not actual 16 kHz pulse loss'),
        geometries=rows,
        interpretation='The U52 area-only and area-plus-path sensitivities miss the 11–12 kV sampled EHT band at 41, 42.504 and 43 V; the full-geometry case also misses the transferred TBY7 lower-current bound. The 25 ns crossing cases retain these outcomes. But the catalog AL is for a U52/H21 set with no intentional gap specified and differs from the provisional B-H model; changing geometry while holding that curve is not a class-valid replacement. The cross-revision U52/54 designation does not prove the .11 core or FONOX U52 identity. A joint core material/gap, winding and return argument remains necessary.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ngspice', type=Path, required=True)
    parser.add_argument('--robotron-pdf', type=Path, required=True)
    parser.add_argument('--fonox-pdf', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args()
    report = run(args.ngspice, args.robotron_pdf, args.fonox_pdf)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print([(r['geometry'], [c['sampled_eht_in_manual_band'] for c in r['cases']])
           for r in report['geometries']])
