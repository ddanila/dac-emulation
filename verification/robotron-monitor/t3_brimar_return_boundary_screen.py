"""Compare conditional T3 return alternatives at the TBY7 rail boundary."""

import argparse
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import t3_brimar_rail_boundary_screen as rail
import t3_drive_pulse_screen as pulse
import t3_loaded_return_screen as returns
import t3_output_stage_sweep as stage
import t3_tp17_path_sweep as tp17


ROOT = Path(__file__).resolve().parent
REF = ROOT / 'reference/k7222-11'
OUTPUT = REF / 't3-brimar-return-boundary-screen.json'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def half_step_case(ngspice, inputs, feed, yoke):
    """Refine only the transient maximum step in the same centred-stage deck."""
    original = rail.centering.replace_once

    def refine(deck, old, new):
        if old == 'tran 100n 5m 4m' and new == 'tran 50n 5m 4m':
            new = 'tran 25n 5m 4m'
        return original(deck, old, new)

    with patch.object(rail.centering, 'replace_once', refine):
        return rail.rail_case(ngspice, inputs, feed, yoke)


def run(ngspice, source_pdf):
    if sha(source_pdf) != rail.SOURCE_PDF_SHA:
        raise ValueError('K7222.11 source scan changed')
    saved = json.loads(rail.OUTPUT.read_text())
    boundary = json.loads(rail.BOUNDARY.read_text())
    catalog = json.loads(rail.CATALOG.read_text())
    if saved['source']['brimar_pdf_sha256'] != catalog['source']['sha256']:
        raise ValueError('TBY7 source changed')
    tby7 = next(row for row in catalog['class_cases'] if row['type'] == 'TBY7')
    yoke = (tby7['line_inductance_h'], tby7['line_resistance_ohm'])
    lower = boundary['axes']['horizontal']['current_pp_a']['bounds'][0]
    eht = saved['manual_eht_bounds_v']
    crossing = saved['threshold']['first_within']['feed_v']
    inputs = pulse.setup()
    transcription, parts, _, _ = stage.source_parts()
    by_id = {part['source_id']: part for part in transcription['components']}
    parts += [by_id['012-6921:' + name] for name in tp17.SOURCE_PARTS]
    rows = []
    refined_rows = []
    for joined in (True, False):
        for cold_mode in ('hv_only_grounded', 'shared_grounded'):
            selected, pins = returns.variant_parts(parts, transcription['ports'],
                                                   joined, cold_mode)
            variant_inputs = (*inputs[:3], selected, *inputs[4:6], pins)
            for feed in (41., crossing, 43.):
                observed = rail.rail_case(ngspice, variant_inputs, feed, yoke)
                rows.append(dict(upper_return_tied=joined, cold_mode=cold_mode,
                                 variant_pins=pins, feed_v=feed,
                                 r5_equivalent_position=observed['r5_equivalent_position'],
                                 yoke_current_pp_a=observed['yoke_current_pp_a'],
                                 eht_at_collector_peak_v=observed['eht_at_collector_peak_v'],
                                 drive_peak_v=observed['drive_peak_v'],
                                 reaches_class_lower_current=observed['yoke_current_pp_a'] >= lower,
                                 sampled_eht_in_manual_band=eht[0] <= observed['eht_at_collector_peak_v'] <= eht[1],
                                 normalized_deck_sha256=observed['normalized_deck_sha256']))
            refined = half_step_case(ngspice, variant_inputs, crossing, yoke)
            refined_rows.append(dict(upper_return_tied=joined, cold_mode=cold_mode,
                                     max_step_ns=25, feed_v=crossing,
                                     yoke_current_pp_a=refined['yoke_current_pp_a'],
                                     eht_at_collector_peak_v=refined['eht_at_collector_peak_v'],
                                     drive_peak_v=refined['drive_peak_v'],
                                     reaches_class_lower_current=refined['yoke_current_pp_a'] >= lower,
                                     sampled_eht_in_manual_band=eht[0] <= refined['eht_at_collector_peak_v'] <= eht[1],
                                     normalized_deck_sha256=refined['normalized_deck_sha256']))
    nominal = next(row for row in rows if row['upper_return_tied'] and
                   row['cold_mode'] == 'hv_only_grounded' and row['feed_v'] == crossing)
    prior = saved['threshold']['first_within']
    if (abs(nominal['yoke_current_pp_a'] - prior['yoke_current_pp_a']) > 1e-6 or
            abs(nominal['eht_at_collector_peak_v'] - prior['eht_at_collector_peak_v']) > .01):
        raise ValueError('nominal return differs from saved rail boundary')
    at_crossing = [row for row in rows if row['feed_v'] == crossing]
    by_return = {(row['upper_return_tied'], row['cold_mode']): row
                 for row in at_crossing}
    refinement = []
    for row in refined_rows:
        original = by_return[row['upper_return_tied'], row['cold_mode']]
        changes = {name: abs(row[name] - original[name]) / abs(original[name])
                   for name in ('yoke_current_pp_a', 'eht_at_collector_peak_v',
                                'drive_peak_v')}
        same_disposition = (row['reaches_class_lower_current'] ==
                            original['reaches_class_lower_current'] and
                            row['sampled_eht_in_manual_band'] ==
                            original['sampled_eht_in_manual_band'])
        refinement.append(dict(upper_return_tied=row['upper_return_tied'],
                               cold_mode=row['cold_mode'],
                               fractional_changes=changes,
                               same_current_and_eht_disposition=same_disposition))
    return dict(
        format='dac-monitor-t3-brimar-return-boundary-screen-v2',
        qualification='conditional 4–5 ms prescribed-base stage and TBY7 comparator; unverified T3 graph/returns and exploratory centring chokes; not installed AE9VT, periodic operation or an A5 freeze',
        source=dict(k7222_11_pdf_sha256=rail.SOURCE_PDF_SHA,
                    brimar_pdf_sha256=catalog['source']['sha256']),
        input_sha256={str(path.relative_to(ROOT)): sha(path) for path in
                      (rail.OUTPUT, rail.BOUNDARY, rail.CATALOG, returns.RETURN_READ,
                       pulse.ac.PARAMETERS, stage.GRAPH, stage.TRANSCRIPTION,
                       stage.MODELS, rail.centering.bridge.MODEL,
                       ROOT/'steady_supply.py', ROOT/'transformer_candidates.py',
                       ROOT/'t3_brimar_rail_boundary_screen.py',
                       ROOT/'t3_centering_return_screen.py',
                       ROOT/'t3_drive_pulse_screen.py',
                       ROOT/'t3_loaded_return_screen.py',
                       ROOT/'t3_output_stage_sweep.py',
                       ROOT/'t3_tp17_path_sweep.py', Path(__file__))},
        ngspice_sha256=sha(ngspice),
        fixed_conditions=dict(yoke_type='TBY7', yoke_line_l_h=yoke[0],
                              yoke_line_r_ohm=yoke[1], centering_link_pair='E1+E2',
                              centering_coil_l_h=.08, r4_position=.5,
                              prescribed_base_edge_ns=200, max_step_ns=50),
        class_lower_current_pp_a=lower, manual_eht_bounds_v=eht,
        prior_boundary_feed_v=crossing, cases=rows,
        half_step_cases=refined_rows, half_step_comparison=refinement,
        all_dispositions_stable_at_25ns=all(row['same_current_and_eht_disposition']
                                             for row in refinement),
        at_prior_crossing=[dict(upper_return_tied=row['upper_return_tied'],
                                cold_mode=row['cold_mode'],
                                current_and_eht_screen_match=(row['reaches_class_lower_current'] and
                                                              row['sampled_eht_in_manual_band']))
                           for row in at_crossing],
        interpretation='At the prior nominal return crossing, three of four conditional return wirings meet the transferred TBY7 lower-current and sampled EHT bands. The tied X1:3/X2:3 plus shared-grounded X1:16/X1:7 combination collapses both outputs; the open-upper-return version does not. All four current/EHT dispositions persist when the maximum step is halved from 50 to 25 ns. This interaction rejects that one pairing only within the assumed graph, stage and rail; it cannot identify the installed return or fix a winding ratio.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ngspice', type=Path, required=True)
    parser.add_argument('--source-pdf', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args()
    report = run(args.ngspice, args.source_pdf)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(report['at_prior_crossing'])
