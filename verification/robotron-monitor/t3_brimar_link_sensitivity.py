"""Test the TBY7 rail crossing against the unresolved centring link and coil.

This is a conditional prescribed-drive sensitivity screen. The L1/L2 bounds
are exploratory, and neither the link position nor AE9VT winding is identified.
"""

import argparse
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import steady_supply
import t3_brimar_rail_boundary_screen as rail
import t3_centering_return_screen as centering
import t3_drive_pulse_screen as pulse


ROOT = Path(__file__).resolve().parent
REF = ROOT / 'reference/k7222-11'
OUTPUT = REF / 't3-brimar-link-sensitivity.json'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(ngspice, source_pdf):
    if sha(source_pdf) != rail.SOURCE_PDF_SHA:
        raise ValueError('K7222.11 source scan changed')
    old = json.loads(rail.OUTPUT.read_text())
    boundary = json.loads(rail.BOUNDARY.read_text())
    catalog = json.loads(rail.CATALOG.read_text())
    if old['source']['brimar_pdf_sha256'] != catalog['source']['sha256']:
        raise ValueError('TBY7 source changed since the rail screen')
    tby7 = next(row for row in catalog['class_cases'] if row['type'] == 'TBY7')
    yoke = (tby7['line_inductance_h'], tby7['line_resistance_ohm'])
    feed = old['threshold']['first_within']['feed_v']
    feed_setting = [feed]
    lower = boundary['axes']['horizontal']['current_pp_a']['bounds'][0]
    coil = steady_supply.ASSEMBLY_BOUNDS['centering_coil_l_h']
    inductances = (coil[1], coil[0], coil[2])
    original_deck = centering.stage.deck

    def with_feed(*args, **kwargs):
        deck = original_deck(*args, **kwargs)
        return centering.replace_once(deck, 'Vfeed h_feed 0 41',
                                      f'Vfeed h_feed 0 {feed_setting[0]:.12g}')

    inputs = pulse.setup()
    rows = []
    thresholds = []
    with patch.object(centering.stage, 'deck', with_feed):
        for pair in (0, 1):
            for inductance in inductances:
                def observe(voltage):
                    feed_setting[0] = voltage
                    result = centering.case(ngspice, inputs, pair, inductance,
                                            yoke=yoke)
                    return dict(feed_v=voltage,
                                current_pp_a=(result['yoke_current_range_a'][1]
                                              - result['yoke_current_range_a'][0]),
                                eht_v=result['eht_at_collector_peak_v'],
                                drive_peak_v=result['drive_peak_v'],
                                deck_sha256=result['normalized_deck_sha256'])

                sampled = observe(feed)
                current = sampled['current_pp_a']
                rows.append(dict(link_pair=('E1+E2' if pair == 0 else 'E3+E4'),
                                 centering_coil_l_h=inductance,
                                 yoke_current_pp_a=current,
                                 reaches_class_lower_current=current >= lower,
                                 eht_at_collector_peak_v=sampled['eht_v'],
                                 drive_peak_v=sampled['drive_peak_v'],
                                 normalized_deck_sha256=sampled['deck_sha256']))
                low, high = observe(41.), observe(43.)
                if not low['current_pp_a'] < lower <= high['current_pp_a']:
                    raise ValueError('41-43 V no longer brackets a class-current crossing')
                for _ in range(8):
                    middle = observe((low['feed_v'] + high['feed_v']) / 2)
                    if middle['current_pp_a'] < lower:
                        low = middle
                    else:
                        high = middle
                thresholds.append(dict(link_pair=('E1+E2' if pair == 0 else 'E3+E4'),
                                       centering_coil_l_h=inductance,
                                       last_below=low,
                                       first_within=high,
                                       first_within_r5_equivalent_position=rail.r5_position_for_feed(high['feed_v']),
                                       bracket_width_v=high['feed_v'] - low['feed_v']))
    by_pair = {(row['link_pair'], row['centering_coil_l_h']): row for row in rows}
    if abs(by_pair[('E1+E2', coil[0])]['yoke_current_pp_a']
           - old['threshold']['first_within']['yoke_current_pp_a']) > 1e-6:
        raise ValueError('nominal link/coil case differs from saved rail crossing')
    pair_deltas = {str(inductance):
                   by_pair[('E3+E4', inductance)]['yoke_current_pp_a']
                   - by_pair[('E1+E2', inductance)]['yoke_current_pp_a']
                   for inductance in inductances}
    coil_span = max(row['yoke_current_pp_a'] for row in rows) - min(
        row['yoke_current_pp_a'] for row in rows)
    return dict(
        format='dac-monitor-t3-brimar-link-sensitivity-v1',
        qualification='conditional 4-5 ms prescribed-base T3/yoke stage at the prior rail crossing; exploratory L1/L2 bounds, unknown E1-E4 pair and unverified T3 graph; not an installed AE9VT or periodic operating point',
        source=dict(k7222_11_pdf_sha256=rail.SOURCE_PDF_SHA,
                    brimar_pdf_sha256=catalog['source']['sha256']),
        input_sha256={str(path.relative_to(ROOT)): sha(path)
                      for path in (rail.OUTPUT, rail.BOUNDARY, rail.CATALOG,
                                   ROOT / 'steady_supply.py',
                                   ROOT / 't3_centering_return_screen.py',
                                   ROOT / 't3_brimar_rail_boundary_screen.py',
                                   ROOT / 't3_drive_pulse_screen.py',
                                   ROOT / 't3_output_stage_sweep.py',
                                   Path(__file__))},
        ngspice_sha256=sha(ngspice),
        fixed_conditions=dict(feed_v=feed,
                              r5_equivalent_position=rail.r5_position_for_feed(feed),
                              yoke_type='TBY7', yoke_line_l_h=yoke[0],
                              yoke_line_r_ohm=yoke[1],
                              centering_coil_r_ohm=steady_supply.ASSEMBLY_BOUNDS['centering_coil_r_ohm'][0],
                              r4_position=.5, prescribed_base_edge_ns=200,
                              max_step_ns=50),
        class_lower_current_pp_a=lower,
        coil_l_h_cases=list(inductances),
        rows=rows,
        threshold_brackets=thresholds,
        threshold_feed_range_v=[min(row['first_within']['feed_v'] for row in thresholds),
                                max(row['first_within']['feed_v'] for row in thresholds)],
        pair_current_difference_a=pair_deltas,
        maximum_absolute_pair_difference_a=max(abs(x) for x in pair_deltas.values()),
        coil_current_span_a=coil_span,
        interpretation='At the sampled rail crossing, swapping the E1+E2 and E3+E4 links scarcely changes TBY7 current under this symmetric bridge. Changing the exploratory coil inductance moves current across the transferred class lower bound, but each sampled coil/link case has a separate class-current crossing within the 41-43 V screen. This isolates L1/L2 as the material uncertainty for this conditional crossing; neither link state nor inductance is source-qualified for the installed board.',
    )


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ngspice', type=Path, required=True)
    parser.add_argument('--source-pdf', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args()
    report = run(args.ngspice, args.source_pdf)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(f"six cases; link delta <= {report['maximum_absolute_pair_difference_a']:.6f} A; "
          f"coil span {report['coil_current_span_a']:.6f} A; "
          f"threshold feeds {report['threshold_feed_range_v'][0]:.3f}-"
          f"{report['threshold_feed_range_v'][1]:.3f} V")
