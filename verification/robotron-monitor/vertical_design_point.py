"""Derive a conditional vertical scan current from documented picture height.

The geometric yoke and electron trajectory are reduced, unmeasured models.
This is an A5 design calculation, not a connected stage measurement or trim.
"""
import argparse
import hashlib
import json
from pathlib import Path

import trajectory
import yoke_geometry

ROOT=Path(__file__).resolve().parent
TARGETS=ROOT/'reference/k7222-11/service-observations.json'
GEOMETRY=ROOT/'profiles/k7222-11-yoke-geometry.json'
DESIGN=ROOT/'reference/k7222-11/design-point.json'
SENSE_SOURCE=ROOT/'reference/k7222-11/page10-output-pair-source-netlist.json'
INVENTORY=ROOT/'reference/k7222-11/inventory.json'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def current_for_half_height(half_height_m,anode_v,field,step_m):
    # Enlarge only the mathematical visibility window so overshoot can be
    # measured. The neck aperture and all magnetic/beam geometry stay fixed.
    diagnostic=field|{'screen_height_m':.25}
    def ordinate(current):
        ray=trajectory.ray(anode_v,350,4000,0,current,overrides=diagnostic,
                           step_m=step_m)
        if 'y_m' not in ray:
            raise ValueError('vertical target hits aperture before screen')
        return ray['y_m']
    low,high=0.,.01
    while ordinate(high)<half_height_m:
        low,high=high,high+.01
        if high>.4:
            raise ValueError('vertical target not reached below 0.4 A')
    for _ in range(24):
        middle=(low+high)/2
        if ordinate(middle)<half_height_m:low=middle
        else:high=middle
    current=(low+high)/2
    observed=ordinate(current)
    if abs(observed-half_height_m)>1e-5:
        raise ValueError('vertical current solve missed target height')
    return dict(peak_current_a=current,observed_half_height_m=observed)


def voltage_budget(peak_current_a,inductance_h,resistance_ohm,trace_s,retrace_s):
    trace_slope=2*peak_current_a/trace_s
    retrace_slope=-2*peak_current_a/retrace_s
    # V=R I + L dI/dt at both ends of each linear segment.
    trace=[inductance_h*trace_slope-resistance_ohm*peak_current_a,
           inductance_h*trace_slope+resistance_ohm*peak_current_a]
    retrace=[inductance_h*retrace_slope+resistance_ohm*peak_current_a,
             inductance_h*retrace_slope-resistance_ohm*peak_current_a]
    return dict(trace_slope_a_per_s=trace_slope,
                retrace_slope_a_per_s=retrace_slope,
                trace_endpoints_v=trace,retrace_endpoints_v=retrace,
                minimum_v=min(trace+retrace),maximum_v=max(trace+retrace),
                total_swing_v=max(trace+retrace)-min(trace+retrace))


def run():
    register=json.loads(TARGETS.read_text())
    design=json.loads(DESIGN.read_text())
    targets={row['quantity']:row for row in register['manual_targets']}
    height=targets['picture_height']
    if height['value']!=145 or height['tolerance']!=15:
        raise ValueError('vertical picture-height source changed')
    points={row['test_point']:row for row in register['waveforms']}
    if {points[n]['model_node'] for n in (7,8)}!={'y1','y2'}:
        raise ValueError('manual yoke-terminal probe mapping changed')
    sense_source=json.loads(SENSE_SOURCE.read_text())
    if (sense_source.get('format')!='dac-monitor-page10-output-pair-source-netlist-v3'
            or not {'R27:1','X2:4'}<=set(sense_source['nets']['Y2_RETURN'])
            or 'R27:2' not in sense_source['nets']['ZERO_RETURN']
            or not {'R29:1','X2:3'}<=set(sense_source['nets']['Y1_OUTPUT'])
            or 'R29:2' not in sense_source['nets']['Y2_RETURN']
            or points[7]['node']!='012-6931:X2:4'):
        raise ValueError('page-10 Y2 sense path is not source established')
    parts={item['id']:item for item in json.loads(INVENTORY.read_text())['parts']}
    r27=parts['012-6931:R27'];r29=parts['012-6931:R29']
    if (r27['value']!=3.9 or r27['tolerance_percent']!=2
            or r29['value']!=430 or r29['tolerance_percent']!=5):
        raise ValueError('page-14 sense and shunt resistor values changed')
    field_model=yoke_geometry.read(GEOMETRY)
    field=field_model['field']
    inductance=field_model['electrical']['yoke_vertical_l']
    resistance=field_model['electrical']['yoke_vertical_r']
    mode=design['mode']
    trace_s=mode['field_period_s']-mode['vertical_retrace_s']
    retrace_s=mode['vertical_retrace_s']
    eht=design['high_voltage_ratio']['eht_target_v']
    anode_values=(eht['minimum'],(eht['minimum']+eht['maximum'])/2,
                  eht['maximum'])
    if abs(trace_s-.018)>1e-12 or abs(retrace_s-.0015)>1e-12 or anode_values!=(11000,11500,12000):
        raise ValueError('documented 2 kByte mode or EHT range changed')
    nominal=current_for_half_height(.0725,anode_values[1],field,.0002)
    nominal['voltage_budget']=voltage_budget(nominal['peak_current_a'],inductance,
                                              resistance,trace_s,retrace_s)
    height_cases=[dict(picture_height_m=value,anode_v=anode_values[1],
                       **current_for_half_height(value/2,anode_values[1],field,.0002))
                  for value in (.130,.145,.160)]
    eht_cases=[dict(picture_height_m=.145,anode_v=value,
                    **current_for_half_height(.0725,value,field,.0002))
               for value in anode_values]
    refinement=[dict(step_m=step,
                     **current_for_half_height(.0725,anode_values[1],field,step))
                for step in (.0002,.0001,.00005)]
    probes={n:points[n]['approximate_swing_v'] for n in (7,8)}
    tolerances={n:points[n]['acceptance_tolerance'] for n in (7,8)}
    sense_current=dict(resistor_source_id=r27['id'],nominal_resistance_ohm=r27['value'],
        resistance_tolerance_fraction=r27['tolerance_percent']/100,
        parallel_shunt_source_id=r29['id'],parallel_shunt_ohm=r29['value'],
        tp7_guideline_vpp=probes[7],
        nominal_total_return_current_swing_a=probes[7]/r27['value'],
        tolerated_total_return_current_swing_a=[
            probes[7]*(1-tolerances[7])/(r27['value']*(1+r27['tolerance_percent']/100)),
            probes[7]*(1+tolerances[7])/(r27['value']*(1-r27['tolerance_percent']/100))],
        geometry_yoke_current_swing_a=2*nominal['peak_current_a'],
        yoke_only_sense_voltage_proxy_vpp=2*nominal['peak_current_a']*r27['value'],
        interpretation='Ohm-law current through R27 includes yoke, R29 shunt and feedback-branch currents; the manual TP7 swing does not uniquely determine yoke current')
    # Separate terminal peak-to-peak values have unknown relative phase and
    # offsets. Their difference must have a swing between these two bounds.
    terminal_difference_bounds=[abs(probes[8]-probes[7]),probes[8]+probes[7]]
    tolerated_difference_bounds=[max(0.,probes[8]*(1-tolerances[8])-
                                      probes[7]*(1+tolerances[7])),
                                 probes[8]*(1+tolerances[8])+
                                 probes[7]*(1+tolerances[7])]
    return dict(format='dac-monitor-vertical-design-point-v2',
                qualification='conditional reduced-geometry design point; no physical tube/yoke measurement or connected voltage score',
                source_sha256=sha(TARGETS),geometry_sha256=sha(GEOMETRY),
                sense_source_sha256=sha(SENSE_SOURCE),inventory_sha256=sha(INVENTORY),
                source_target=dict(picture_height_mm=height['value'],
                    tolerance_mm=height['tolerance'],source=height['source'],
                    native_2k_mode_source=mode['source']),
                assumed_conditions=dict(grid2_v=350,focus_v=4000,
                    nominal_anode_v=anode_values[1],
                    anode_bounds_v=[anode_values[0],anode_values[2]],
                    trace_s=trace_s,retrace_s=retrace_s,
                    field_start_m=field['yoke_start_m'],
                    field_length_m=field['yoke_length_m'],
                    internal_neck_radius_m=field['neck_radius_m'],
                    vertical_tesla_per_amp=field['vertical_tesla_per_amp'],
                    vertical_inductance_h=inductance,
                    vertical_resistance_ohm=resistance),
                nominal=nominal,height_cases=height_cases,eht_cases=eht_cases,
                trajectory_refinement=refinement,
                manual_yoke_terminal_guidelines=dict(
                    tp7_swing_vpp=probes[7],tp8_swing_vpp=probes[8],
                    possible_difference_swing_vpp=terminal_difference_bounds,
                    accepted_tolerances={str(n):tolerances[n] for n in (7,8)},
                    toleranced_possible_difference_swing_vpp=tolerated_difference_bounds,
                    required_ideal_ramp_swing_vpp=nominal['voltage_budget']['total_swing_v'],
                    tp7_sense_branch=sense_current,
                    inside_toleranced_possibility=(tolerated_difference_bounds[0]<=
                        nominal['voltage_budget']['total_swing_v']<=
                        tolerated_difference_bounds[1]),
                    interpretation='separate terminal swings do not fix differential waveform phase or DC level; compare only as a consistency screen'),
                limitations=[
                    'The 40 mm axial field, 10 mm inner neck radius, 20 mH and 10 ohm yoke are unmeasured reduced-model assumptions.',
                    'Test points 1-6 constrain upstream stage waveforms, not yoke current directly; points 7 and 8 are separate terminal voltages.',
                    'R27 converts TP7 voltage into total sense current; its shunt and feedback branches prevent equating that directly with yoke current.',
                    'Linear current ramps and V=RI+L dI/dt omit driver loss, coupling and yoke saturation.',
                    'This calculation does not settle the horizontal T3 graph or constitute a sustained connected-stage score.'])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    report=run()
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(f"conditional vertical peak current {report['nominal']['peak_current_a']:.4f} A")


if __name__=='__main__':
    main()
