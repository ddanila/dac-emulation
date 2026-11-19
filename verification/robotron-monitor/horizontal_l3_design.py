"""Check L3/R35 line-output branch against an isolated retrace shunt budget."""
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


def solve(l_h,r_ohm,r35_ohm,frequency_hz):
    deck='\n'.join([
        'L3/R35 isolated AC branch',
        f'.param horizontal_linearity_l={l_h:.15g}',
        f'.param horizontal_linearity_r={r_ohm:.15g}',
        MODEL.read_text(),
        'Vtest hot 0 DC 0 AC 1',
        'XL3 hot 0 HORIZONTAL_LINEARITY',
        f'R35 hot 0 {r35_ohm:.15g}',
        '.control', f'ac lin 1 {frequency_hz:.15g} {frequency_hz:.15g}',
        'print i(Vtest)', 'quit', '.endc', '.end',
    ])+'\n'
    result=subprocess.run(['ngspice','-b'],input=deck,text=True,
                          capture_output=True,check=True)
    output=result.stdout+result.stderr
    if 'Error:' in output or 'error:' in output:raise ValueError(output)
    values=re.findall(r'i\(vtest\) = ([^\n]+)',output)
    if len(values)!=1:raise ValueError('missing AC branch current: '+output)
    measured=complex(*[float(value) for value in values[0].split(',')])
    branch=1/(r_ohm+2j*math.pi*frequency_hz*l_h)
    expected=-(branch+1/r35_ohm)
    return dict(inductance_h=l_h,resistance_ohm=r_ohm,frequency_hz=frequency_hz,
                line_branch_admittance_s=[branch.real,branch.imag],
                ngspice_source_current_a=[measured.real,measured.imag],
                calculated_source_current_a=[expected.real,expected.imag],
                shunt_to_inductor_current_ratio=abs(r_ohm+2j*math.pi*frequency_hz*l_h)/r35_ohm,
                source_current_error_a=abs(measured-expected))


def run():
    inventory=json.loads(INVENTORY.read_text())
    parts={part['id']:part for part in inventory['parts']}
    r35=parts['012-6921:R35']
    if r35['value']!=82:raise ValueError('R35 value changed: rederive L3 budget')
    minimum_r35=r35['value']*(1-r35['tolerance_percent']/100)
    profile=json.loads(PROFILE.read_text())['parameters']
    l=profile['horizontal_linearity_l'];r=profile['horizontal_linearity_r']
    design=json.loads(DESIGN.read_text())
    line_hz=1/design['mode']['line_period_s']
    retrace_hz=1/(2*design['mode']['horizontal_retrace_s'])
    maximum_l=math.sqrt((.25*minimum_r35)**2-r['maximum']**2)/(2*math.pi*retrace_hz)
    with tempfile.TemporaryDirectory() as directory:
        out=Path(directory);xml=out/'output.xml'
        lab.run_command(['kicad-cli','sch','export','netlist','--format','kicadxml',
                         '-o',str(xml),str(SHEET)],out,out/'export.log')
        exported=reference.source_connectivity(xml,inventory,'012-6921',
                                                steady_supply.OUTPUT_CONTRACTS)
    components={part['source_id']:part for part in exported}
    l3_nodes=components['012-6921:L3']['nodes']
    r35_nodes=components['012-6921:R35']['nodes']
    cases={
        'minimum_l_line':solve(l['minimum'],r['nominal'],r35['value'],line_hz),
        'nominal_line':solve(l['nominal'],r['nominal'],r35['value'],line_hz),
        'nominal_retrace':solve(l['nominal'],r['nominal'],r35['value'],retrace_hz),
        'maximum_l_retrace':solve(l['maximum'],r['maximum'],minimum_r35,retrace_hz),
    }
    maximum_r=.02*minimum_r35
    passed=(l3_nodes==r35_nodes==['h_hot','h_linout']
            and l['maximum']<=maximum_l and r['maximum']<=maximum_r
            and cases['maximum_l_retrace']['shunt_to_inductor_current_ratio']<=.25
            and all(case['source_current_error_a']<1e-5 for case in cases.values()))
    return dict(format='dac-monitor-horizontal-l3-design-v1',
        qualification='conditional isolated L3/R35 branch check; not a source-validated full output stage, factory L3 value or A3/A5 score',
        source_transcription_sha256=sha(TRANSCRIPTION),sheet_sha256=sha(SHEET),
        profile_sha256=sha(PROFILE),model_sha256=sha(MODEL),
        inventory_sha256=sha(INVENTORY),
        documented=dict(r35_ohm=r35['value'],r35_tolerance_percent=r35['tolerance_percent'],
                        minimum_r35_ohm=minimum_r35,r35_source=r35['source'],
                        line_frequency_hz=line_hz,retrace_half_cycle_hz=retrace_hz,
                        timing_source=design['mode']['source']),
        model_nodes=dict(l3=l3_nodes,r35=r35_nodes),
        design_rule=dict(maximum_l_h_for_r35_current_at_most_one_quarter_of_l3_at_retrace=maximum_l,
                         maximum_r_ohm_for_two_percent_of_r35=maximum_r,
                         equation='|I_R35/I_L3| = sqrt(R_L3^2 + (2*pi*f*L3)^2) / R35_min',
                         limitation='The 25% branch-current and 2% resistance budgets are engineering operating choices, not printed L3 specifications.'),
        cases=cases,
        open_checks=['The L3/R35/C25 page-4 branch has not passed the independent full-page A1 netlist comparison',
                     'Original L3 inductance, DC/core loss, current/saturation and thermal limits are unknown',
                     'The isolated branch has no C25, yoke, T3 or connected waveform loading'],
        passed=passed)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    report=run();args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(f"{len(report['cases'])} AC cases; max shunt fraction {report['cases']['maximum_l_retrace']['shunt_to_inductor_current_ratio']:.2%}; passed={report['passed']}")
    if not report['passed']:raise SystemExit(1)
