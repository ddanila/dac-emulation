"""Screen the TBY7 current boundary over the source-derived R5 rail range."""

import argparse
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import steady_supply
import t3_centering_return_screen as centering
import t3_drive_pulse_screen as pulse


ROOT = Path(__file__).resolve().parent
REF = ROOT / 'reference/k7222-11'
OUTPUT = REF / 't3-brimar-rail-boundary-screen.json'
BOUNDARY = REF / 'a5-yoke-class-boundary.json'
CATALOG = REF / 'yoke-brimar-110deg-comparator.json'
STAGE = REF / 't3-yoke-brimar-stage-screen.json'
INVENTORY = REF / 'inventory.json'
DESIGN = REF / 'design-point.json'
SOURCE_PDF_SHA = '3c435063815af483a0fa98823a8a95a4178359e64f759344ee03cc0300e292dd'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def r5_position_for_feed(feed_v, nominal_v=41):
    """Invert the documented R6/R5 divider's active rail-scale proxy."""
    position = ((2400+1000*.63)*nominal_v/feed_v-2400)/1000
    if not 0 <= position <= 1:
        raise ValueError('feed voltage is outside the R5 equivalent travel')
    if abs(nominal_v*steady_supply.r5_rail_scale(position)-feed_v) > 1e-9:
        raise ValueError('R5 inverse differs from the active supply model')
    return position


def rail_case(ngspice, inputs, feed_v, yoke):
    """Change only the source-addressed 41P feed in centering.case's deck."""
    original_deck = centering.stage.deck

    def with_feed(*args, **kwargs):
        deck = original_deck(*args, **kwargs)
        return centering.replace_once(deck, 'Vfeed h_feed 0 41',
                                      f'Vfeed h_feed 0 {feed_v:.12g}')

    with patch.object(centering.stage, 'deck', with_feed):
        observed = centering.case(ngspice, inputs, 0, .08, yoke=yoke)
    current_pp = (observed['yoke_current_range_a'][1]
                  - observed['yoke_current_range_a'][0])
    return dict(feed_v=feed_v, r5_equivalent_position=r5_position_for_feed(feed_v),
                yoke_current_pp_a=current_pp,
                eht_at_collector_peak_v=observed['eht_at_collector_peak_v'],
                drive_peak_v=observed['drive_peak_v'],
                normalized_deck_sha256=observed['normalized_deck_sha256'],
                full_stage_observation=observed)


def run(ngspice, source_pdf):
    if sha(source_pdf) != SOURCE_PDF_SHA:
        raise ValueError('K7222.11 source scan changed')
    inventory = {row['id']: row for row in json.loads(INVENTORY.read_text())['parts']}
    for name, value in (('R5', 1000), ('R6', 2400), ('R7', 30000)):
        if inventory['012-6931:'+name]['value'] != value:
            raise ValueError('R5 feedback-divider source value changed')
    design = json.loads(DESIGN.read_text())
    catalog = json.loads(CATALOG.read_text())
    boundary = json.loads(BOUNDARY.read_text())
    stage = json.loads(STAGE.read_text())
    if (catalog['source']['sha256'] != boundary['source']['sha256'] or
            catalog['source']['sha256'] != stage['source']['sha256']):
        raise ValueError('TBY7 manufacturer source differs across reports')
    tby7 = next(row for row in catalog['class_cases'] if row['type'] == 'TBY7')
    winding = (tby7['line_inductance_h'], tby7['line_resistance_ohm'])
    current_bounds = boundary['axes']['horizontal']['current_pp_a']['bounds']
    eht_bounds = design['high_voltage_ratio']['eht_target_v']
    inputs = pulse.setup()
    cases = [rail_case(ngspice, inputs, feed, winding)
             for feed in (39., 41., 43.)]
    saved = next(row for row in stage['class_cases']
                 if row['catalog_type'] == 'TBY7')
    if (abs(cases[1]['yoke_current_pp_a']-saved['model_yoke_current_pp_a']) > 1e-6 or
            abs(cases[1]['eht_at_collector_peak_v']-saved['eht_at_collector_peak_v']) > .01):
        raise ValueError('41 V case differs from saved TBY7 stage')
    if not cases[1]['yoke_current_pp_a'] < current_bounds[0] <= cases[2]['yoke_current_pp_a']:
        raise ValueError('41/43 V cases no longer bracket the class lower current')
    low, high = cases[1], cases[2]
    for _ in range(10):
        mid = rail_case(ngspice, inputs, (low['feed_v']+high['feed_v'])/2,
                        winding)
        if mid['yoke_current_pp_a'] < current_bounds[0]:
            low = mid
        else:
            high = mid
    for row in cases+[low, high]:
        row['within_class_current_bounds'] = (current_bounds[0] <=
            row['yoke_current_pp_a'] <= current_bounds[1])
        row['within_manual_eht_band_at_sample'] = (eht_bounds['minimum'] <=
            row['eht_at_collector_peak_v'] <= eht_bounds['maximum'])
    return dict(
        format='dac-monitor-t3-brimar-rail-boundary-screen-v1',
        qualification='conditional prescribed-base 4–5 ms T3 stage; not periodic, not installed AE9VT, not an A5 winding-ratio freeze',
        source=dict(k7222_11_pdf_sha256=SOURCE_PDF_SHA,
                    r5_schematic_pdf_page=10, r5_parts_pdf_page=13,
                    brimar_pdf_sha256=catalog['source']['sha256']),
        input_hashes={str(path.relative_to(ROOT)): sha(path)
                      for path in (BOUNDARY, CATALOG, STAGE, INVENTORY,
                                   DESIGN, ROOT/'steady_supply.py',
                                   ROOT/'t3_centering_return_screen.py',
                                   ROOT/'t3_drive_pulse_screen.py',
                                   ROOT/'t3_output_stage_sweep.py',
                                   Path(__file__))},
        ngspice_sha256=sha(ngspice),
        fixed_conditions=dict(yoke_type='TBY7', yoke_line_l_h=winding[0],
                              yoke_line_r_ohm=winding[1],
                              centering_link_pair='E1+E2',
                              centering_coil_l_h=.08,
                              r4_position=.5,
                              prescribed_base_edge_ns=200,
                              max_step_ns=50,
                              nominal_feed_v=41),
        source_derived_r5_scale_equation='feed_v = 41 * (2400+1000*0.63)/(2400+1000*position)',
        class_current_bounds_pp_a=current_bounds,
        manual_eht_bounds_v=[eht_bounds['minimum'], eht_bounds['maximum']],
        cases=cases,
        threshold=dict(last_below=low, first_within=high,
                       feed_bracket_width_v=high['feed_v']-low['feed_v']),
        interpretation='Within this unverified T3 graph and prescribed drive, raising only the 41P feed from 41 to 43 V moves TBY7 current into the transferred class lower bound while sampled EHT remains within 11–12 kV. The rail change corresponds to an R5-equivalent position inside physical travel. This conditional match does not establish AE9VT current, periodic operation, the remaining rail responses, or a T3 turns ratio.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ngspice', type=Path, required=True)
    parser.add_argument('--source-pdf', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args()
    report = run(args.ngspice, args.source_pdf)
    args.output.write_text(json.dumps(report, indent=2)+'\n')
    t = report['threshold']['first_within']
    print(f"class lower-current threshold: {t['feed_v']:.4f} V, R5 position {t['r5_equivalent_position']:.4f}")
