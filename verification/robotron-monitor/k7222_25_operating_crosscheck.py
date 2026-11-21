"""Compare the AE9VT-named K7222.25 manual with the partial .11 design point."""

import argparse
import hashlib
import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parent
REF = ROOT / 'reference/k7222-11'
READ = REF / 'k7222-25-horizontal-source-read.json'
DESIGN = REF / 'design-point.json'
ASSEMBLY = REF / 'assembly.json'
RAIL = REF / 't3-brimar-rail-boundary-screen.json'
LINK = REF / 't3-brimar-link-sensitivity.json'
PDF = ROOT.parents[1] / 'build/monitor/phase-a/sources/pc1715-servicemanual.pdf'
OUTPUT = REF / 'k7222-25-operating-crosscheck.json'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run():
    read = json.loads(READ.read_text())
    design = json.loads(DESIGN.read_text())
    assembly = json.loads(ASSEMBLY.read_text())
    rail = json.loads(RAIL.read_text())
    link = json.loads(LINK.read_text())
    if sha(PDF) != read['source']['local_pdf_sha256']:
        raise ValueError('K7222.25 source PDF changed')
    for view in read['source']['views']:
        render = ROOT.parents[1] / view['render']
        if render.is_file() and sha(render) != view['render_sha256']:
            raise ValueError('K7222.25 source render changed: ' + view['render'])
    stage = read['horizontal_stage_k7222_25']
    if (stage['yoke_type'] != 'AE9VT'
            or not assembly['yoke']['type'].startswith(stage['yoke_type'] + ' ')
            or stage['yoke_amplitude_tap_numbers'] != [2, 3, 4]):
        raise ValueError('K7222.25 yoke or tap reading changed')
    mode = design['mode']
    timing = read['timing_k7222_25']
    deltas = dict(trace_us=round(timing['trace_us'] - mode['horizontal_trace_s'] * 1e6, 3),
                  retrace_us=round(timing['retrace_us'] - mode['horizontal_retrace_s'] * 1e6, 3),
                  line_us=round(timing['line_us'] - mode['line_period_s'] * 1e6, 3),
                  field_ms=round(timing['field_ms'] - mode['field_period_s'] * 1e3, 3))
    boost = stage['boost_at_c21_v']
    if not stage['boost_voltage_reference'].startswith('across C21'):
        raise ValueError('K7222.25 boost voltage reference changed')
    ideal_multiplier = design['collector_flyback']['ideal_ratio_to_trace_supply']
    rail_range = stage['supply_41p_v']
    # C21 is between 41P and the boost node in the .11 transcription. The
    # manual describes voltage *across* C21, so trace-node voltage is their sum.
    corrected_trace = [rail_range[0] + boost[0], rail_range[1] + boost[1]]
    corrected_collector = [ideal_multiplier * value for value in corrected_trace]
    eht = design['high_voltage_ratio']['eht_target_v']
    corrected_hv_ratio = [eht['minimum'] / corrected_collector[1],
                          eht['maximum'] / corrected_collector[0]]
    candidate = design['collector_flyback']
    if (candidate['candidate_41p_feed_v']['bounds'] != rail_range
            or candidate['candidate_c21_differential_v']['bounds'] != boost
            or candidate['candidate_trace_node_v']['bounds'] != corrected_trace
            or not math.isclose(candidate['candidate_boosted_collector_peak_v']['minimum'],
                                corrected_collector[0], rel_tol=1e-10)
            or not math.isclose(candidate['candidate_boosted_collector_peak_v']['maximum'],
                                corrected_collector[1], rel_tol=1e-10)):
        raise ValueError('design-point boost reference or arithmetic differs')
    ratio = design['high_voltage_ratio']['ratio_if_boost_case_is_correct']
    if (not math.isclose(ratio['minimum'], corrected_hv_ratio[0], rel_tol=1e-10)
            or not math.isclose(ratio['maximum'], corrected_hv_ratio[1], rel_tol=1e-10)):
        raise ValueError('design-point EHT ratio differs from corrected boost')
    feed = rail['threshold']['first_within']['feed_v']
    sweep = link['threshold_feed_range_v']
    if not (rail_range[0] <= sweep[0] <= feed <= sweep[1] <= rail_range[1]):
        raise ValueError('conditional rail crossing exceeds K7222.25 comparator range')
    return dict(
        format='dac-monitor-k7222-25-operating-crosscheck-v3',
        qualification='same-named-yoke cross-revision timing, rail and boost comparison; no K7222.11 T3 ratio, tap map, installed yoke current or source-driven waveform qualification',
        input_sha256={str(path.relative_to(ROOT)): sha(path)
                      for path in (READ, DESIGN, ASSEMBLY, RAIL, LINK, Path(__file__))},
        source_pdf_sha256=sha(PDF),
        k7222_25_yoke_type=stage['yoke_type'],
        k7222_25_timing=timing,
        k7222_11_timing=dict(trace_us=mode['horizontal_trace_s'] * 1e6,
                              retrace_us=mode['horizontal_retrace_s'] * 1e6,
                              line_us=mode['line_period_s'] * 1e6,
                              field_ms=mode['field_period_s'] * 1e3),
        k7222_25_minus_k7222_11_timing=deltas,
        k7222_25_41p_v=rail_range,
        k7222_25_c21_differential_voltage_v=boost,
        design_point_uses_c21_differential_reference=True,
        corrected_conditional_trace_node_v=corrected_trace,
        corrected_conditional_ideal_collector_peak_v=corrected_collector,
        corrected_conditional_eht_to_collector_ratio=corrected_hv_ratio,
        conditional_tby7_nominal_crossing_feed_v=feed,
        conditional_tby7_choke_sweep_crossing_feed_v=sweep,
        crossing_inside_k7222_25_41p_range=True,
        finding='The later Robotron stage names AE9VT and independently gives 60-70 V across C21; the .11 page-4 annotation agrees. C21 lies between 41P and the boost node in the .11 graph, and the partial design point now sums the two voltages to a conditional 99-113 V trace-node range. The TBY7 rail crossings fit the later 39-43 V 41P range, but neither revision qualifies the .11 T3 graph or actual collector pulse.',
        excluded_transfer=read['excluded_transfer'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args()
    result = run()
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print('K7222.25 41P comparator contains conditional crossing:',
          result['conditional_tby7_choke_sweep_crossing_feed_v'])
