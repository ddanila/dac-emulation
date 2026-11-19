"""Bound the selected two-choke L4 base-drive path as a conditional branch."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import tempfile

import lab
import reference
import steady_supply

ROOT=Path(__file__).resolve().parent
PROFILE=ROOT/'profiles/k7222-11-horizontal-oscillator.json'
MODEL=ROOT/'circuits/k7222-11-horizontal-models.cir'
SHEET=ROOT/'circuits/k7222-11-horizontal-output.kicad_sch'
INVENTORY=ROOT/'reference/k7222-11/inventory.json'
DESIGN=ROOT/'reference/k7222-11/design-point.json'
TRANSCRIPTION=ROOT/'reference/k7222-11/horizontal-output-transcription.json'


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def pulse_current(l_h,r_ohm,voltage_v,duration_s):
    deck='\n'.join([
        'L4 parallel base-path conditional pulse',
        f'.param horizontal_compensation_l={l_h:.15g}',
        f'.param horizontal_compensation_r={r_ohm:.15g}',
        MODEL.read_text(),
        f'Vtest hot 0 PULSE(0 {voltage_v:.15g} 0 1n 1n {duration_s*2:.15g} {duration_s*4:.15g})',
        'XL41 hot 0 HORIZONTAL_COMPENSATION',
        'XL42 hot 0 HORIZONTAL_COMPENSATION',
        '.control',f'tran 0.1u {duration_s:.15g}',
        f'meas tran i_end FIND i(Vtest) AT={duration_s:.15g}',
        'quit','.endc','.end',
    ])+'\n'
    result=subprocess.run(['ngspice','-b'],input=deck,text=True,capture_output=True,check=True)
    output=result.stdout+result.stderr
    if 'Error:' in output or 'error:' in output:raise ValueError(output)
    match=re.search(r'i_end\s*=\s*([-+\d.eE]+)',output)
    if not match:raise ValueError('missing pulse current: '+output)
    measured=-float(match.group(1))
    expected=2*voltage_v/r_ohm*(-math.expm1(-r_ohm*duration_s/l_h))
    return dict(ngspice_current_a=measured,calculated_current_a=expected,
                absolute_error_a=abs(measured-expected))


def run():
    inventory=json.loads(INVENTORY.read_text())
    parts={part['id']:part for part in inventory['parts']}
    ids=[f'012-6921:L4:{n}' for n in (1,2,3)]
    if len({parts[part]['description'] for part in ids})!=1:
        raise ValueError('L4 stock identities differ: rederive shared model')
    profile=json.loads(PROFILE.read_text())['parameters']
    l=profile['horizontal_compensation_l'];r=profile['horizontal_compensation_r']
    design=json.loads(DESIGN.read_text())
    trace=design['mode']['horizontal_trace_s']
    duration=trace/3
    voltage=1.0
    target=.5
    # The source-driven RL branch needs only 1 V across the two equal chokes.
    # This is a condition on the T2/V18 interface, not a prediction of it.
    maximum_l=-r['maximum']*duration/math.log(1-target*r['maximum']/(2*voltage))
    maximum_r=2*(.25*voltage)/target
    with tempfile.TemporaryDirectory() as directory:
        out=Path(directory);xml=out/'output.xml'
        lab.run_command(['kicad-cli','sch','export','netlist','--format','kicadxml',
                         '-o',str(xml),str(SHEET)],out,out/'export.log')
        exported=reference.source_connectivity(xml,inventory,'012-6921',
                                                steady_supply.OUTPUT_CONTRACTS)
    components={part['source_id']:part for part in exported}
    nodes={part:components[part]['nodes'] for part in ids}
    maximum_case=pulse_current(l['maximum'],r['maximum'],voltage,duration)
    passed=(nodes[ids[0]]==nodes[ids[1]]==['h_outputbase','h_outbase']
            and nodes[ids[2]]==['h_outbase','h_outbase']
            and l['maximum']<=maximum_l and r['maximum']<=maximum_r
            and maximum_case['ngspice_current_a']>=target
            and maximum_case['absolute_error_a']<1e-4)
    return dict(format='dac-monitor-horizontal-l4-design-v1',
        qualification='conditional isolated base-path operating budget; no source-validated E2 setting, actual T2 drive, original L4 values or A3/A5 score',
        source_transcription_sha256=sha(TRANSCRIPTION),sheet_sha256=sha(SHEET),
        profile_sha256=sha(PROFILE),model_sha256=sha(MODEL),
        inventory_sha256=sha(INVENTORY),
        documented=dict(horizontal_trace_s=trace,timing_source=design['mode']['source'],
                        printed_type=parts[ids[0]]['description'],
                        stock_source=parts[ids[0]]['source']),
        model_nodes=nodes,
        design_rule=dict(base_current_target_a=target,branch_voltage_headroom_v=voltage,
                         turn_on_budget_fraction_of_trace=1/3,turn_on_budget_s=duration,
                         maximum_l_h_per_coil_at_r_max=maximum_l,
                         maximum_r_ohm_per_coil_for_quarter_volt_drop_at_target=maximum_r,
                         current_equation='I_pair(t) = 2*V/R*(1-exp(-R*t/L))',
                         limitation='0.5 A target is a BU508AF-class inductive switching comparator, not a measured V18 requirement; 1 V at L4 is a conditional drive-headroom budget, not an observed T2 output.'),
        worst_case_pulse=maximum_case,
        open_checks=['E2 jumper setting and page-4 L4 connectivity require independent source comparison',
                     'Actual T2 secondary voltage and source resistance under V18 loading are unknown',
                     'Original L4 inductance, winding loss, magnetic coupling, current rating and thermal limits are unknown',
                     'L4:3 is bridged in this selected configuration, so its electrical effect is unobservable here'],
        passed=passed)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    report=run();args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(f"one-third-trace branch current {report['worst_case_pulse']['ngspice_current_a']:.3f} A; passed={report['passed']}")
    if not report['passed']:raise SystemExit(1)
