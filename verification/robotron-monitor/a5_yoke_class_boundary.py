"""Derive a labelled A5 yoke-current and trace-voltage class boundary.

This uses a source-paired Brimar winding as an electrical/current comparator.
It does not identify the installed AE9VT or replace the trajectory profile.
"""

import argparse
import hashlib
import itertools
import json
from pathlib import Path

import yoke_brimar_110deg_comparator as brimar


ROOT = Path(__file__).resolve().parent
REF = ROOT / 'reference/k7222-11'
OUTPUT = REF / 'a5-yoke-class-boundary.json'
DESIGN = REF / 'design-point.json'
REGISTER = REF / 'class-typical-register.json'
STAGE = REF / 't3-yoke-brimar-stage-screen.json'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def trace_voltage(inductance_h, resistance_ohm, current_pp_a, trace_s):
    """Ideal series RL voltage range for a centred, linear current trace."""
    inductive_v = inductance_h * current_pp_a / trace_s
    resistive_end_v = resistance_ohm * current_pp_a / 2
    return dict(inductive_v=inductive_v,
                start_v=inductive_v-resistive_end_v,
                end_v=inductive_v+resistive_end_v)


def axis_boundary(axis, case, rows, trace_s):
    prefix = 'line' if axis == 'horizontal' else 'field'
    entries = [rows['AE9VT.TBY7_candidate_'+prefix+'_'+suffix]
               for suffix in ('inductance', 'resistance', 'current_proxy')]
    inductance, resistance, current = entries
    current_nominal = case['transferred_current_nominal_pp_a'][axis]
    current_bounds = case['transferred_current_bounds_pp_a'][axis]
    if (inductance['value'] != case[prefix+'_inductance_h'] or
            resistance['value'] != case[prefix+'_resistance_ohm'] or
            current['value'] != current_nominal or
            current['bounds'] != current_bounds):
        raise ValueError('A6 TBY7 register and source-paired comparator diverge')
    nominal = trace_voltage(inductance['value'], resistance['value'],
                            current_nominal, trace_s)
    corners = [trace_voltage(l, r, i, trace_s)
               for l, r, i in itertools.product(inductance['bounds'],
                                                resistance['bounds'],
                                                current_bounds)]
    return dict(
        winding=dict(inductance_h=inductance['value'],
                     inductance_bounds_h=inductance['bounds'],
                     resistance_ohm=resistance['value'],
                     resistance_bounds_ohm=resistance['bounds']),
        current_pp_a=dict(nominal=current_nominal, bounds=current_bounds),
        current_peak_a=dict(nominal=current_nominal/2,
                            bounds=[x/2 for x in current_bounds]),
        trace_s=trace_s,
        nominal_ideal_rl_voltage_v=nominal,
        independent_corner_ideal_rl_voltage_v={
            key: [min(row[key] for row in corners),
                  max(row[key] for row in corners)]
            for key in ('inductive_v', 'start_v', 'end_v')},
        voltage_scope='Yoke winding only, centred linear trace; excludes S-correction capacitors, centring bridge, flyback, leakage and stage loading')


def run(source_pdf):
    catalog = brimar.run(source_pdf)
    if json.loads(brimar.OUTPUT.read_text()) != catalog:
        raise ValueError('saved Brimar comparator differs from manufacturer PDF')
    design = json.loads(DESIGN.read_text())
    register = json.loads(REGISTER.read_text())
    stage = json.loads(STAGE.read_text())
    rows = {row['id']: row for row in register['entries']}
    case = next(row for row in catalog['class_cases'] if row['type'] == 'TBY7')
    stage_case = next(row for row in stage['class_cases']
                      if row['catalog_type'] == 'TBY7')
    if stage_case['line_inductance_h'] != case['line_inductance_h'] or stage_case['line_resistance_ohm'] != case['line_resistance_ohm']:
        raise ValueError('conditional stage is not the TBY7 winding')
    mode = design['mode']
    vertical_trace_s = mode['field_period_s']-mode['vertical_retrace_s']
    axes = dict(
        horizontal=axis_boundary('horizontal', case, rows,
                                 mode['horizontal_trace_s']),
        vertical=axis_boundary('vertical', case, rows, vertical_trace_s))
    h = axes['horizontal']['current_pp_a']
    stage_current = stage_case['model_yoke_current_pp_a']
    return dict(
        format='dac-monitor-a5-yoke-class-boundary-v1',
        qualification='class-typical electrical/current boundary, not installed AE9VT identity, B31G22 field geometry or a frozen A5 design point',
        source=catalog['source'],
        input_hashes={str(path.relative_to(ROOT)): sha(path)
                      for path in (brimar.OUTPUT, DESIGN, REGISTER, STAGE,
                                   Path(__file__))},
        comparator_type='TBY7',
        target=catalog['target'],
        transfer_equation=catalog['transfer_equation'],
        transfer_uncertainty=catalog['transfer_uncertainty_basis'],
        axes=axes,
        conditional_stage=dict(
            status='prescribed-drive, unverified T3 graph and return, nonperiodic 4–5 ms sample',
            source_report=str(STAGE.relative_to(ROOT)),
            sampled_yoke_current_pp_a=stage_current,
            below_class_lower_bound_pp_a=h['bounds'][0]-stage_current,
            nominal_current_shortfall_fraction=1-stage_current/h['nominal'],
            sampled_eht_v=stage_case['eht_at_collector_peak_v'],
            sampled_drive_peak_v=stage_case['drive_peak_v']),
        next_use='Use as a bounded class candidate for A5/B3 T3 and yoke sensitivity; preserve the active yoke and ray profile until its field geometry and the T3 drive/return are bounded.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-pdf', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args()
    report = run(args.source_pdf)
    args.output.write_text(json.dumps(report, indent=2)+'\n')
    print('TBY7 class boundary:',
          report['axes']['horizontal']['current_pp_a']['nominal'],
          report['axes']['vertical']['current_pp_a']['nominal'],
          'A p-p')
