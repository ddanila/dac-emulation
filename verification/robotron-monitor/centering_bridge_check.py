"""Isolated DC and 16 kHz loading check of the source-addressed page-9 bridge."""
import argparse
import json
from pathlib import Path
import re
import subprocess

import page9_centering_compare
import steady_supply

ROOT=Path(__file__).resolve().parent
MODEL=ROOT/'circuits/k7222-11-centering-models.cir'
RATE_HZ=16000


def simulate(position,pair,coil_l_h,*,bridge=True,ac=False):
    p={key:value[0] for key,value in steady_supply.ASSEMBLY_BOUNDS.items()}
    a=max(1.,p['centering_r4_total_ohm']*position)
    b=max(1.,p['centering_r4_total_ohm']*(1-position))
    lines=['Page 9 horizontal centring isolated check',
        f'.param centering_coil_l_h={coil_l_h:.15g}',
        f".param centering_coil_r_ohm={p['centering_coil_r_ohm']:.15g}",
        f'.param centering_r4_a_ohm={a:.15g}',
        f'.param centering_r4_b_ohm={b:.15g}',
        f".param centering_r2_ohm={p['centering_r2_ohm']:.15g}",
        MODEL.read_text()]
    if bridge:
        lines += ['X971 hy2 centering_a CENTERING_CHOKE',
                  'X972 hy1 centering_w CENTERING_CHOKE',
                  'X973 centering_a centering_b centering_w CENTERING_POT',
                  'R974 centering_b centering_c {centering_r2_ohm}']
        links=[('centering_a','0'),('centering_c','p12')] if pair==0 else [
              ('centering_c','0'),('centering_a','p12')]
        lines += [f'Rlink{i} {left} {right} 1m' for i,(left,right) in enumerate(links)]
    lines += [f"Ryoke hy1 yoke_mid {p['yoke_horizontal_r']:.15g}",
              f"Lyoke yoke_mid hy2 {p['yoke_horizontal_l']:.15g}",
              'Ryokeleak hy2 0 1G',
              'Vp12 p12 0 DC 12 AC 0']
    if ac:lines.append('Vac hy1 hy2 DC 0 AC 1')
    lines += ['.control',f'ac lin 1 {RATE_HZ} {RATE_HZ}' if ac else 'op',
              'print i(Vac)' if ac else 'print i(Lyoke)','quit','.endc','.end']
    result=subprocess.run(['ngspice','-b'],input='\n'.join(lines)+'\n',
                          text=True,capture_output=True,check=True)
    output=result.stdout+result.stderr
    if 'Error:' in output or 'error:' in output:raise ValueError(output)
    pattern=r'i\('+('vac' if ac else 'lyoke')+r'\) = ([^\n]+)'
    match=re.search(pattern,output)
    if not match:raise ValueError('ngspice did not report requested current: '+output)
    values=[float(v) for v in match.group(1).split(',')]
    return complex(*values) if ac else values[0]


def run():
    comparison=page9_centering_compare.run()
    if not comparison['passed']:raise ValueError('source bridge comparison failed')
    p={key:value[0] for key,value in steady_supply.ASSEMBLY_BOUNDS.items()}
    dc=[]
    for pair in (0,1):
        for position in (0.,.5,1.):
            actual=simulate(position,pair,p['centering_coil_l_h'])
            expected=steady_supply.centering_bridge_dc_estimate(position,pair,
                p['centering_r2_ohm'],p['centering_r4_total_ohm'],
                p['centering_coil_r_ohm'],p['yoke_horizontal_r'])
            error=abs(actual-expected)
            dc.append(dict(strap_pair='E1+E2' if pair==0 else 'E3+E4',
                r4_position=position,ngspice_yoke_current_a=actual,
                thevenin_estimate_a=expected,error_a=error))
    baseline=simulate(.5,0,p['centering_coil_l_h'],bridge=False,ac=True)
    loading=[]
    for inductance in (steady_supply.ASSEMBLY_BOUNDS['centering_coil_l_h'][1],
                       p['centering_coil_l_h'],
                       steady_supply.ASSEMBLY_BOUNDS['centering_coil_l_h'][2]):
        full=simulate(.5,0,inductance,ac=True)
        ratio=abs(full-baseline)/abs(baseline)
        loading.append(dict(coil_inductance_h=inductance,
            bridge_to_yoke_ac_current_ratio_at_16khz=ratio,
            full_source_current_a=[full.real,full.imag]))
    passed=all(row['error_a']<2e-6 for row in dc) and loading[1]['bridge_to_yoke_ac_current_ratio_at_16khz']<.05
    return dict(format='dac-monitor-page9-centering-bridge-check-v1',
        qualification='isolated DC and 16 kHz source loading; not a connected horizontal-stage or installed-link validation',
        source_netlist_sha256=comparison['source_netlist_sha256'],
        sheet_sha256=comparison['sheet_sha256'],model_sha256=page9_centering_compare.sha(MODEL),
        nominal_parameters=dict(r2_ohm=p['centering_r2_ohm'],r4_total_ohm=p['centering_r4_total_ohm'],
                                coil_r_ohm=p['centering_coil_r_ohm'],
                                yoke_r_ohm=p['yoke_horizontal_r'],
                                yoke_l_h=p['yoke_horizontal_l']),
        design_basis='At 16 kHz, 80 mH has 8.04 kohm reactance versus 0.4 kohm for the nominal 4 mH yoke; the isolated AC check resolves the two-branch loading.',
        dc_error_limit_a=2e-6,
        dc_error_note='The Thevenin estimate omits the two 1 milliohm numerical link contacts and the 1 Gohm yoke ground leak.',
        dc_cases=dc,ac_baseline_yoke_source_current_a=[baseline.real,baseline.imag],
        ac_loading=loading,nominal_ac_loading_limit=.05,
        open_checks=['Coil construction and inductance/resistance are not printed',
                     'Installed E1-E4 jumper pair is not identified',
                     'The connected horizontal output and native-frame sensitivity remain unqualified'],
        passed=passed)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    report=run();args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(f"6 DC cases and 3 AC bounds checked; passed={report['passed']}")
    if not report['passed']:raise SystemExit(1)
