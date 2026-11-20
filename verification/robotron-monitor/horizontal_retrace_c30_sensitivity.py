"""Bound the optional C30 retrace-capacitor choice in the loaded output stage."""
import argparse
import copy
import json
import math
from pathlib import Path

import t2_l4_output_stage_sweep as driver
import transformer_candidates

ROOT = Path(__file__).resolve().parent
DESIGN = driver.stage.DESIGN
TRANSCRIPTION = driver.stage.TRANSCRIPTION


def resonance_inductance(retrace_s, capacitance_f):
    return (retrace_s/math.pi)**2/capacitance_f


def run():
    stage = driver.stage
    design = json.loads(DESIGN.read_text())
    retrace_s = design['mode']['horizontal_retrace_s']
    caps = {row['source_id']: row for row in
            design['horizontal_resonance']['candidate_parallel_capacitors']}
    c27 = caps['012-6921:C27']
    c30 = caps['012-6921:C30']
    _, output_parts, l3_r, l3_l = stage.source_parts()
    for cap in (c27, c30):
        part = next(row for row in output_parts if row['source_id'] == cap['source_id'])
        if part['nodes'] != ['h_hot', '0'] or float(part['value']) != cap['value_f']:
            raise ValueError('retrace capacitor source transcription changed')
    graph = json.loads(stage.GRAPH.read_text())
    parameters = copy.deepcopy(json.loads(stage.AC_LOSS.read_text()))
    parameters['groups']['high_voltage'][0]['turns']['value'] = 1768
    driver_parts = driver.source_parts()
    accepted = set(json.loads(stage.SIGN.read_text())['accepted_candidate_ids'])
    candidate = next(item for item in transformer_candidates.enumerate_candidates(graph)
                     if item['id'] in accepted)
    rows = []
    for c30_populated in (True, False):
        selected = (output_parts if c30_populated else
                    [part for part in output_parts if part['source_id'] != c30['source_id']])
        for polarity, on_trace in (('model', False), ('reversed', True)):
            result = driver.simulate(graph, parameters, candidate, selected,
                                     l3_r, l3_l, driver_parts, ratio=3,
                                     l4_h=5e-6, on_trace=on_trace,
                                     secondary_reversed=polarity == 'reversed',
                                     reltol=.002)
            rows.append({'c30_populated': c30_populated,
                         't2_secondary_polarity': polarity,
                         'v13_drive_phase': 'on_trace' if on_trace else 'off_trace',
                         'result': result})
    sensitivity = []
    for polarity in ('model', 'reversed'):
        populated = next(row['result'] for row in rows if row['c30_populated']
                         and row['t2_secondary_polarity'] == polarity)
        absent = next(row['result'] for row in rows if not row['c30_populated']
                      and row['t2_secondary_polarity'] == polarity)
        if populated['status'] == absent['status'] == 'complete':
            changes = {key: (absent[key]-populated[key])/populated[key] for key in
                       ('collector_peak_v', 'eht_final_v',
                        'flyback_width_us_at_10pct_swing_median',
                        'driver_collector_swing_v')}
            sensitivity.append({'t2_secondary_polarity': polarity,
                                'absent_relative_to_populated': changes})
    analytic = []
    for c30_populated in (False, True):
        selected = (c27, c30) if c30_populated else (c27,)
        nominal = sum(cap['value_f'] for cap in selected)
        minimum = sum(cap['value_f']*(1-cap['tolerance_fraction']) for cap in selected)
        maximum = sum(cap['value_f']*(1+cap['tolerance_fraction']) for cap in selected)
        analytic.append({'c30_populated': c30_populated,
                         'effective_capacitance_f': {'nominal': nominal,
                                                     'minimum': minimum,
                                                     'maximum': maximum},
                         'effective_inductance_h_for_16us_retrace': {
                             'nominal': resonance_inductance(retrace_s, nominal),
                             'minimum': resonance_inductance(retrace_s, maximum),
                             'maximum': resonance_inductance(retrace_s, minimum)}})
    return {
        'format': 'dac-monitor-retrace-c30-sensitivity-v1',
        'qualification': 'conditional C30 population and loaded 5 ms stage sensitivity; not a source-confirmed jumper/population choice, periodic result or A3/A5 pass',
        'source_hashes': {path.name: stage.sha(path) for path in
                          (DESIGN, TRANSCRIPTION, driver.OSC, stage.GRAPH,
                           stage.AC_LOSS, stage.MODELS, stage.SIGN)},
        'assumptions': [
            'C27 is kept at its documented 10 nF; C30 is either absent or populated at its documented 1 nF. The source transcription marks C30 as optional.',
            'Analytic inductance is the effective half-cycle resonance of the whole output network, not a yoke or T3 winding value.',
            'Loaded cases use the same 1768-turn, AC-loss T3 candidate, nominal T2 ratio/L4 values, ideal feed/boost and prescribed V13 base drive as the T2/L4 sweep, with Gear reltol 0.002.',
            'Only the 4–5 ms window is summarized; periodic steady state and the source page-3/4 seam remain unverified.',
        ],
        'retrace_s': retrace_s, 'analytic_scenarios': analytic,
        'loaded_cases': rows, 'loaded_sensitivity': sensitivity,
        'exceeds_2pct_stage_sensitivity': any(
            abs(case['absent_relative_to_populated'][key]) > .02
            for case in sensitivity for key in ('collector_peak_v', 'eht_final_v')),
        'analysis_valid': len(rows) == 4 and len(sensitivity) == 2,
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = run()
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(f"{len(report['loaded_sensitivity'])}/2 polarity comparisons complete; "
          f"above 2% sensitivity={report['exceeds_2pct_stage_sensitivity']}")
    if not report['analysis_valid']:
        raise SystemExit(1)
