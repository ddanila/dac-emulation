"""Screen effective T3 inductance factor and its U52-class gap equivalent."""

import argparse
import copy
import hashlib
import json
import math
from pathlib import Path

import t3_brimar_rail_boundary_screen as rail
import t3_drive_pulse_screen as pulse
import t3_u52_core_class_screen as core_class


ROOT = Path(__file__).resolve().parent
REF = ROOT / 'reference/k7222-11'
OUTPUT = REF / 't3-u52-al-gap-screen.json'
MU0_H_PER_M = 4 * math.pi * 1e-7


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def effective_al_nh(core):
    h, b = core['h_a_per_m'], core['b_t']
    center = h.index(0)
    slope = (b[center+1]-b[center])/(h[center+1]-h[center])
    return core['area_m2']['value']/core['length_m']['value']*slope*1e9


def equivalent_gap_m(area_m2, target_al_nh, catalog_al_nh):
    """Extra series reluctance as a simple net air gap, without fringing."""
    return MU0_H_PER_M*area_m2*(1/(target_al_nh*1e-9)-1/(catalog_al_nh*1e-9))


def run(ngspice, robotron_pdf, fonox_pdf):
    source = json.loads(core_class.SOURCE.read_text())
    if sha(robotron_pdf) != source['robotron']['sha256'] or sha(fonox_pdf) != source['fonox']['sha256']:
        raise ValueError('U52 comparison source changed')
    saved = json.loads(rail.OUTPUT.read_text())
    prior_core = json.loads(core_class.OUTPUT.read_text())
    catalog = json.loads(rail.CATALOG.read_text())
    boundary = json.loads(rail.BOUNDARY.read_text())
    yoke_row = next(row for row in catalog['class_cases'] if row['type'] == 'TBY7')
    yoke = (yoke_row['line_inductance_h'], yoke_row['line_resistance_ohm'])
    lower = boundary['axes']['horizontal']['current_pp_a']['bounds'][0]
    eht = saved['manual_eht_bounds_v']
    crossing = saved['threshold']['first_within']['feed_v']
    base = pulse.setup()
    active_al = effective_al_nh(base[1]['core'])
    if abs(active_al - 375) > 1e-9:
        raise ValueError('active coupled-core AL changed')
    area = source['fonox']['effective_area_mm2']*1e-6
    length = source['fonox']['effective_path_length_mm']*1e-3
    al_nominal = source['fonox']['al_nh_per_turn2']
    tolerance = source['fonox']['al_tolerance_fraction']
    al_values = (active_al, al_nominal*(1-tolerance), al_nominal,
                 al_nominal*(1+tolerance))
    base_h = base[1]['core']['h_a_per_m']
    rows = []
    for al in al_values:
        inputs = list(base)
        inputs[1] = copy.deepcopy(base[1])
        core = inputs[1]['core']
        core['area_m2']['value'] = area
        core['length_m']['value'] = length
        ungapped_model_al = effective_al_nh(core)
        core['h_a_per_m'] = [h*ungapped_model_al/al for h in base_h]
        if abs(effective_al_nh(core)-al) > 1e-8:
            raise ValueError('coupled-core AL scale differs from requested value')
        cases = []
        for feed in (41., crossing, 43.):
            observed = rail.rail_case(ngspice, tuple(inputs), feed, yoke)
            cases.append(dict(feed_v=feed, max_step_ns=50,
                              yoke_current_pp_a=observed['yoke_current_pp_a'],
                              eht_at_collector_peak_v=observed['eht_at_collector_peak_v'],
                              drive_peak_v=observed['drive_peak_v'],
                              current_in_transferred_class=observed['yoke_current_pp_a'] >= lower,
                              sampled_eht_in_manual_band=eht[0] <= observed['eht_at_collector_peak_v'] <= eht[1],
                              normalized_deck_sha256=observed['normalized_deck_sha256']))
        refined = core_class.half_step(ngspice, tuple(inputs), crossing, yoke)
        cases.append(dict(feed_v=crossing, max_step_ns=25,
                          yoke_current_pp_a=refined['yoke_current_pp_a'],
                          eht_at_collector_peak_v=refined['eht_at_collector_peak_v'],
                          drive_peak_v=refined['drive_peak_v'],
                          current_in_transferred_class=refined['yoke_current_pp_a'] >= lower,
                          sampled_eht_in_manual_band=eht[0] <= refined['eht_at_collector_peak_v'] <= eht[1],
                          normalized_deck_sha256=refined['normalized_deck_sha256']))
        rows.append(dict(effective_al_nh_per_turn2=al,
                         normalized_origin_h_scale=ungapped_model_al/al,
                         cases=cases))
    nominal = next(row for row in rows[0]['cases'] if row['feed_v'] == crossing and row['max_step_ns'] == 50)
    old = saved['threshold']['first_within']
    if (abs(nominal['yoke_current_pp_a']-old['yoke_current_pp_a']) > 1e-6 or
            abs(nominal['eht_at_collector_peak_v']-old['eht_at_collector_peak_v']) > .01):
        raise ValueError('375 nH equivalence differs from saved active-core rail screen')
    if abs(prior_core['geometries'][-1]['implied_model_al_nh_per_turn2']-ungapped_model_al) > 1e-8:
        raise ValueError('U52 geometry-only AL differs from saved screen')
    gaps_mm = [equivalent_gap_m(area, active_al, al)*1000 for al in al_values[1:]]
    return dict(
        format='dac-monitor-t3-u52-al-gap-screen-v1',
        qualification='conditional linear coupled-T3 magnetizing sensitivity on U52-class geometry and TBY7 yoke, 4–5 ms prescribed drive; not an identified .11 core, physical gap, winding ratio or A5 freeze',
        source_pdf_sha256=dict(robotron=sha(robotron_pdf), fonox=sha(fonox_pdf)),
        source_read_sha256=sha(core_class.SOURCE),
        input_sha256={str(path.relative_to(ROOT)): sha(path) for path in
                      (rail.OUTPUT, rail.BOUNDARY, rail.CATALOG, core_class.OUTPUT,
                       pulse.ac.PARAMETERS, rail.centering.bridge.MODEL,
                       rail.centering.stage.GRAPH, rail.centering.stage.TRANSCRIPTION,
                       rail.centering.stage.MODELS, ROOT/'magnetics.py',
                       ROOT/'steady_supply.py', ROOT/'transformer_candidates.py',
                       ROOT/'t3_brimar_rail_boundary_screen.py',
                       ROOT/'t3_centering_return_screen.py',
                       ROOT/'t3_drive_pulse_screen.py',
                       ROOT/'t3_u52_core_class_screen.py', Path(__file__))},
        ngspice_sha256=sha(ngspice),
        fixed_conditions=dict(core_area_m2=area, core_path_length_m=length,
                              yoke_type='TBY7', yoke_line_l_h=yoke[0],
                              yoke_line_r_ohm=yoke[1], centering_link_pair='E1+E2',
                              centering_coil_l_h=.08, prescribed_base_edge_ns=200,
                              provisional_turns_and_loss_unchanged=True),
        backend_semantics='The passive coupled model uses only the B-H origin slope for Lmag=N^2*AL; scaling H changes effective AL without a nonlinear saturation or material-loss model.',
        class_lower_current_pp_a=lower, manual_eht_bounds_v=eht,
        prior_boundary_feed_v=crossing, active_model_al_nh_per_turn2=active_al,
        catalog_al_nh_per_turn2=dict(nominal=al_nominal,
                                     bounds=[al_values[1], al_values[-1]]),
        extra_reluctance_equivalent_gap=dict(
            equation='g_eff=mu0*A_e*(1/AL_target - 1/AL_catalog)',
            target_al_nh_per_turn2=active_al,
            catalog_al_cases_nh_per_turn2=list(al_values[1:]),
            gap_mm=gaps_mm,
            limitations='Net extra-reluctance air-gap proxy only. Fringing, two-pole distribution, actual .11 core/material and winding are unknown; this is not an installed gap measurement.'),
        cases=rows,
        interpretation='The 375 nH/turn² effective-AL case exactly reproduces the prior conditional TBY7 rail crossing even on U52 geometry, because the coupled backend depends on N²*AL rather than geometry separately. All sampled FONOX catalog AL cases miss the transferred TBY7 lower current at 41, 42.504 and 43 V; EHT is nonmonotone and the 1475 nH case can enter its band without the current match. An excess-reluctance equivalent gap of 0.183–0.237 mm would map the catalog AL spread to the conditional 375 nH value, but the .11 core/gap and T3 graph remain unknown. This identifies an effective magnetic parameter for the fallback sensitivity, not a frozen physical core or winding design.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ngspice', type=Path, required=True)
    parser.add_argument('--robotron-pdf', type=Path, required=True)
    parser.add_argument('--fonox-pdf', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args()
    report = run(args.ngspice, args.robotron_pdf, args.fonox_pdf)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print([(row['effective_al_nh_per_turn2'],
            [(c['current_in_transferred_class'], c['sampled_eht_in_manual_band'])
             for c in row['cases']]) for row in report['cases']])
