"""Screen a source-paired, unequal centring-choke class against the TBY7 stage."""

import argparse
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import t3_brimar_rail_boundary_screen as rail
import t3_centering_return_screen as centering
import t3_drive_pulse_screen as pulse


ROOT = Path(__file__).resolve().parent
REF = ROOT / 'reference/k7222-11'
OUTPUT = REF / 't3-brimar-asymmetric-choke-screen.json'
SOURCE_URL = ('https://www.worldradiohistory.com/Archive-Service-Magazine/'
              '50s/Service-1954-03.pdf')
COIL_ASSIGNMENTS = ((0.016, 0.070), (0.070, 0.016))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(ngspice, source_pdf):
    if sha(source_pdf) != rail.SOURCE_PDF_SHA:
        raise ValueError('K7222.11 scan changed')
    old = json.loads(rail.OUTPUT.read_text())
    boundary = json.loads(rail.BOUNDARY.read_text())
    catalog = json.loads(rail.CATALOG.read_text())
    if old['source']['brimar_pdf_sha256'] != catalog['source']['sha256']:
        raise ValueError('TBY7 source changed')
    tby7 = next(row for row in catalog['class_cases'] if row['type'] == 'TBY7')
    yoke = (tby7['line_inductance_h'], tby7['line_resistance_ohm'])
    lower_current = boundary['axes']['horizontal']['current_pp_a']['bounds'][0]
    feed = old['threshold']['first_within']['feed_v']
    feed_setting = [feed]
    coil_setting = [None]
    original_deck = centering.stage.deck
    original_replace = centering.replace_once
    common_model = centering.bridge.MODEL.read_text()
    choke, pot = common_model.split('.subckt CENTERING_POT', 1)

    def with_unequal_coils(deck, old_text, new_text):
        if old_text == 'Rhy2ref hy2 0 1G':
            l1_h, l2_h = coil_setting[0]
            model = '\n'.join([
                choke.replace('CENTERING_CHOKE', 'CENTERING_CHOKE_L1')
                     .replace('{centering_coil_l_h}', f'{l1_h:.15g}'),
                choke.replace('CENTERING_CHOKE', 'CENTERING_CHOKE_L2')
                     .replace('{centering_coil_l_h}', f'{l2_h:.15g}'),
                '.subckt CENTERING_POT' + pot,
            ])
            new_text = original_replace(new_text, common_model, model)
            new_text = original_replace(new_text,
                'X971 hy2 centering_a CENTERING_CHOKE',
                'X971 hy2 centering_a CENTERING_CHOKE_L1')
            new_text = original_replace(new_text,
                'X972 hy1 centering_w CENTERING_CHOKE',
                'X972 hy1 centering_w CENTERING_CHOKE_L2')
        return original_replace(deck, old_text, new_text)

    def with_feed(*args, **kwargs):
        deck = original_deck(*args, **kwargs)
        return original_replace(deck, 'Vfeed h_feed 0 41',
                                f'Vfeed h_feed 0 {feed_setting[0]:.12g}')

    inputs = pulse.setup()
    rows = []
    with patch.object(centering.stage, 'deck', with_feed), \
         patch.object(centering, 'replace_once', with_unequal_coils):
        for link in (0, 1):
            for inductances in COIL_ASSIGNMENTS:
                coil_setting[0] = inductances
                def observe(voltage):
                    feed_setting[0] = voltage
                    result = centering.case(ngspice, inputs, link, 0.080,
                                            yoke=yoke)
                    return dict(feed_v=voltage,
                                current_pp_a=(result['yoke_current_range_a'][1]
                                              - result['yoke_current_range_a'][0]),
                                eht_v=result['eht_at_collector_peak_v'],
                                drive_peak_v=result['drive_peak_v'],
                                deck_sha256=result['normalized_deck_sha256'])

                sampled = observe(feed)
                low, high = observe(41.), observe(43.)
                if not low['current_pp_a'] < lower_current <= high['current_pp_a']:
                    raise ValueError('41–43 V does not bracket class current')
                for _ in range(8):
                    mid = observe((low['feed_v'] + high['feed_v']) / 2)
                    if mid['current_pp_a'] < lower_current:
                        low = mid
                    else:
                        high = mid
                rows.append(dict(link_pair='E1+E2' if link == 0 else 'E3+E4',
                                 l1_h=inductances[0], l2_h=inductances[1],
                                 current_at_old_crossing=sampled,
                                 last_below=low, first_within=high,
                                 first_within_r5_equivalent_position=rail.r5_position_for_feed(high['feed_v'])))

    currents = [row['current_at_old_crossing']['current_pp_a'] for row in rows]
    link_differences = []
    for inductances in COIL_ASSIGNMENTS:
        a, b = (next(row for row in rows if row['link_pair'] == pair
                     and (row['l1_h'], row['l2_h']) == inductances)
                for pair in ('E1+E2', 'E3+E4'))
        link_differences.append(dict(l1_h=inductances[0], l2_h=inductances[1],
                                     difference_a=(b['current_at_old_crossing']['current_pp_a']
                                                   - a['current_at_old_crossing']['current_pp_a'])))
    return dict(
        format='dac-monitor-t3-brimar-asymmetric-choke-screen-v1',
        qualification='cross-era 16/70 mH isolating-choke class paired with a conditional 4–5 ms prescribed-drive T3/TBY7 stage; not an installed L1/L2 identification, source-qualified X2:4 waveform or periodic operating point',
        source=dict(url=SOURCE_URL, publication='SERVICE, March 1954, Color TV Developments, pp. 8 and 90',
                    reading='RCA-supplied tricolor deflection circuit uses 16 mH and 70 mH isolating chokes between the horizontal winding terminals and a centering control; its yoke, tube and power stage differ from K7222.11',
                    k7222_11_pdf_sha256=rail.SOURCE_PDF_SHA,
                    brimar_pdf_sha256=catalog['source']['sha256']),
        input_sha256={str(path.relative_to(ROOT)): sha(path)
                      for path in (rail.OUTPUT, rail.BOUNDARY, rail.CATALOG,
                                   centering.bridge.MODEL,
                                   ROOT / 't3_centering_return_screen.py',
                                   ROOT / 't3_brimar_rail_boundary_screen.py',
                                   ROOT / 't3_drive_pulse_screen.py',
                                   ROOT / 't3_output_stage_sweep.py',
                                   Path(__file__))},
        ngspice_sha256=sha(ngspice),
        fixed_conditions=dict(feed_v=feed, yoke_type='TBY7',
                              yoke_line_l_h=yoke[0], yoke_line_r_ohm=yoke[1],
                              r4_position=.5, prescribed_base_edge_ns=200,
                              max_step_ns=50),
        class_lower_current_pp_a=lower_current,
        rows=rows,
        current_span_at_old_crossing_a=max(currents) - min(currents),
        link_pair_differences_at_old_crossing=link_differences,
        maximum_absolute_link_pair_difference_a=max(abs(row['difference_a'])
                                                    for row in link_differences),
        threshold_feed_range_v=[min(row['first_within']['feed_v'] for row in rows),
                                max(row['first_within']['feed_v'] for row in rows)],
        interpretation='Unequal, source-paired class chokes test whether the previous symmetric-choke link insensitivity transfers to a plausible asymmetric bridge. All values remain conditional on a different-era class and the unverified T3 graph; only the installed L1/L2 and E1–E4 configuration can close A5.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ngspice', type=Path, required=True)
    parser.add_argument('--source-pdf', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args()
    report = run(args.ngspice, args.source_pdf)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(f"{len(report['rows'])} cases; link delta <={report['maximum_absolute_link_pair_difference_a']:.6f} A; "
          f"threshold feeds {report['threshold_feed_range_v'][0]:.3f}–{report['threshold_feed_range_v'][1]:.3f} V")
