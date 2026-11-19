"""Check a bounded L1 supply choke against the printed R42/C22 feed network."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess

import page4_l1_compare

ROOT=Path(__file__).resolve().parent
PROFILE=ROOT/'profiles/k7222-11-horizontal-oscillator.json'
INVENTORY=ROOT/'reference/k7222-11/inventory.json'
DESIGN=ROOT/'reference/k7222-11/design-point.json'
MODEL=ROOT/'circuits/k7222-11-horizontal-models.cir'


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def solve(l_h,r_ohm,r42_ohm,c22_f,frequency_hz):
    lines=['Horizontal L1 isolated source-feed check',
           f'.param horizontal_choke_r={r_ohm:.15g}',
           f'.param horizontal_choke_l={l_h:.15g}',MODEL.read_text(),
           'Vrail p41 0 DC 41 AC 1',f'R42 p41 h_chokein {r42_ohm:.15g}',
           'X1122 h_chokein h_feed HORIZONTAL_CHOKE',
           f'C22 h_feed 0 {c22_f:.15g}',
           'Iload h_feed 0 DC 1 AC 0',
           '.control','op','print v(h_feed)',
           f'ac lin 1 {frequency_hz:.15g} {frequency_hz:.15g}',
           'print v(h_feed)','quit','.endc','.end']
    output=subprocess.run(['ngspice','-b'],input='\n'.join(lines)+'\n',
                          text=True,capture_output=True,check=True)
    text=output.stdout+output.stderr
    if 'Error:' in text or 'error:' in text:raise ValueError(text)
    values=re.findall(r'v\(h_feed\) = ([^\n]+)',text)
    if len(values)!=2:raise ValueError('ngspice did not report both feed analyses: '+text)
    dc=float(values[0]);ac=complex(*[float(v) for v in values[1].split(',')])
    w=2*math.pi*frequency_hz
    zc=1/(1j*w*c22_f)
    expected_ac=zc/(r42_ohm+r_ohm+1j*w*l_h+zc)
    expected_dc=41-r42_ohm-r_ohm
    return dict(inductance_h=l_h,resistance_ohm=r_ohm,
        lc_corner_hz=1/(2*math.pi*math.sqrt(l_h*c22_f)),
        ngspice_dc_feed_v_at_1a=dc,design_dc_feed_v_at_1a=expected_dc,
        ngspice_ac_feed_ratio_at_line=abs(ac),design_ac_feed_ratio_at_line=abs(expected_ac),
        ac_complex=[ac.real,ac.imag],
        dc_error_v=abs(dc-expected_dc),ac_complex_error=abs(ac-expected_ac))


def run():
    comparison=page4_l1_compare.run()
    if not comparison['passed']:raise ValueError('page-4 L1 source comparison failed')
    inventory={part['id']:part for part in json.loads(INVENTORY.read_text())['parts']}
    r42=inventory['012-6921:R42'];c22=inventory['012-6921:C22']
    if r42['value']!=6.8 or c22['value']!=.00022:
        raise ValueError('R42 or C22 source value changed; rederive L1')
    profile=json.loads(PROFILE.read_text())['parameters']
    l=profile['horizontal_choke_l'];r=profile['horizontal_choke_r']
    design=json.loads(DESIGN.read_text())
    frequency=1/design['mode']['line_period_s']
    minimum_for_fivefold_separation=25/((2*math.pi*frequency)**2*c22['value'])
    cases={
        'minimum_inductance':solve(l['minimum'],r['nominal'],r42['value'],c22['value'],frequency),
        'nominal':solve(l['nominal'],r['nominal'],r42['value'],c22['value'],frequency),
        'maximum_inductance':solve(l['maximum'],r['nominal'],r42['value'],c22['value'],frequency),
        'minimum_resistance':solve(l['nominal'],r['minimum'],r42['value'],c22['value'],frequency),
        'maximum_resistance':solve(l['nominal'],r['maximum'],r42['value'],c22['value'],frequency)}
    selected=json.loads((ROOT/'reference/k7222-11/page4-l1-source-read.json').read_text())
    passed=(l['minimum']>=minimum_for_fivefold_separation
            and r['maximum']<=.1*r42['value']+1e-12
            and cases['nominal']['ngspice_ac_feed_ratio_at_line']<.005
            and cases['minimum_inductance']['ngspice_ac_feed_ratio_at_line']<.01
            and all(case['dc_error_v']<1e-5 and case['ac_complex_error']<1e-7
                    for case in cases.values()))
    return dict(format='dac-monitor-horizontal-l1-design-v1',
        qualification='conditional isolated passive filter and 1 A DC-drop check; not connected output-stage or original L1 qualification',
        source_pdf_sha256=selected['source']['pdf_sha256'],
        source_read_sha256=sha(ROOT/'reference/k7222-11/page4-l1-source-read.json'),
        comparison_sha256=sha(ROOT/'reference/k7222-11/page4-l1-comparison.json'),
        profile_sha256=sha(PROFILE),model_sha256=sha(MODEL),
        documented=dict(r42_ohm=r42['value'],r42_source=r42['source'],
                        c22_f=c22['value'],c22_source=c22['source'],
                        line_frequency_hz=frequency,line_source=design['mode']['source']),
        design_rules=dict(minimum_l_h_for_corner_at_most_line_over_five=minimum_for_fivefold_separation,
                          maximum_coil_r_ohm_for_ten_percent_added_dc_drop=.1*r42['value'],
                          ac_transfer_equation='Zc / (R42 + Rcoil + j*omega*Lcoil + Zc)',
                          dc_drop_equation='1 A * (R42 + Rcoil)'),
        cases=cases,selected_crossing_stress=selected['crossing_decision'],
        open_checks=['The crossing is selected by circuit stress rather than an unambiguous printed dot',
                     'Original L1 inductance, copper/core loss, saturation and thermal limits are unknown',
                     'C22 ESR and connected flyback supply loading are not included in this isolated check'],
        passed=passed)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    report=run();args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(f"{len(report['cases'])} isolated cases; nominal 16 kHz feed ratio {report['cases']['nominal']['ngspice_ac_feed_ratio_at_line']:.4%}; passed={report['passed']}")
    if not report['passed']:raise SystemExit(1)
