"""Measure the active V21 diode against two documented EHT rectifier classes."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

import horizontal_diode_check as diode

ROOT = Path(__file__).resolve().parent
MODEL = ROOT/'circuits/k7222-11-horizontal-models.cir'
CASES = (
    dict(name='Rectron R12000H', source='https://www.rectron.com/public/product_datasheets/r12000h.pdf',
         forward_a=.01, forward_max_v=37.5, reverse_v=12000, reverse_max_a=2e-6,
         recovery_forward_a=.002, recovery_reverse_a=.004, recovery_limit_s=100e-9,
         recovery_return_a=.001, recovery_return_basis='25% of specified reverse current; proxy because Rectron does not state a return threshold',
         fixture_forward_v=1.15, fixture_reverse_v=-.05, fixture_r_ohm=100,
         fixture_hold_s=1e-6, fixture_end_s=3e-6, fixture_step_s=.5e-9,
         fixture_transition_s=.05e-9),
    dict(name='Semtech SDH15K', source='https://www.semtech.com/uploads/design-support/SG-SEMTECH-PD-DATABOOK.pdf',
         forward_a=.2, forward_max_v=20., reverse_v=15000, reverse_max_a=2e-6,
         recovery_forward_a=.05, recovery_reverse_a=.1, recovery_limit_s=2.5e-6,
         recovery_return_a=.025, recovery_return_basis='manufacturer 25 mA return threshold; discrete devices before assembly',
         fixture_forward_v=6.2, fixture_reverse_v=-9.6, fixture_r_ohm=5,
         fixture_hold_s=2e-6, fixture_end_s=6e-6, fixture_step_s=1e-9,
         fixture_transition_s=1e-9),
)


def recovery(model_line, case):
    hold, transition, end, step = (case[key] for key in
                                    ('fixture_hold_s','fixture_transition_s',
                                     'fixture_end_s','fixture_step_s'))
    source = (f'VIN src 0 PWL(0 {case["fixture_forward_v"]} '
              f'{hold} {case["fixture_forward_v"]} '
              f'{hold+transition} {case["fixture_reverse_v"]} '
              f'{end} {case["fixture_reverse_v"]})\n'
              f'RLOAD src a {case["fixture_r_ohm"]}\n'
              'VSENSE a b 0\nD1 b 0 HOR_HV_RECT')
    with tempfile.TemporaryDirectory() as directory:
        out=Path(directory);trace=out/'recovery.txt';deck=out/'recovery.cir'
        deck.write_text('\n'.join(('V21 long-held recovery comparison','.temp 25',model_line,
                                   source,'.control',f'tran {step} {end}',
                                   'set wr_singlescale',f'wrdata {trace} i(vsense)',
                                   'quit','.endc','.end'))+'\n')
        result=subprocess.run(['ngspice','-n','-b',str(deck)],capture_output=True,text=True)
        if result.returncode:
            raise RuntimeError('ngspice recovery failed: '+result.stdout[-500:]+result.stderr[-500:])
        rows=[tuple(map(float,row.split())) for row in trace.read_text().splitlines()]
    if any(len(row)!=2 for row in rows):raise ValueError('malformed V21 recovery trace')
    start=next(i for i,(time,_) in enumerate(rows) if time>=hold)
    forward=rows[start-2][1]
    reverse=min(current for _,current in rows[start:])
    zero=diode.crossing(rows,0.,'falling',start-2)
    returned=diode.crossing(rows,-case['recovery_return_a'],'rising',start)
    return dict(forward_current_a=forward,peak_reverse_current_a=reverse,
                zero_crossing_s=zero,return_to_threshold_s=returned,
                reverse_recovery_s=returned-zero,
                return_threshold_a=case['recovery_return_a'],
                forward_hold_s=hold,source_transition_s=transition,
                sample_step_s=step)


def run():
    line=diode.model_line('HOR_HV_RECT')
    cap=diode.solve(line,'VAC a 0 0 AC 1\nD1 a 0 HOR_HV_RECT',
                    'ac lin 1 1meg 1meg\nlet cap=-imag(i(vac))/(2*pi*frequency)',
                    ['cap'])['cap']
    rows=[]
    for case in CASES:
        forward=diode.solve(line,f'IF 0 a {case["forward_a"]}\nD1 a 0 HOR_HV_RECT',
                            'op',['v(a)'])['v(a)']
        reverse=diode.solve(line,f'VR a 0 -{case["reverse_v"]}\nD1 a 0 HOR_HV_RECT',
                            'op',['i(vr)'])['i(vr)']
        trace=recovery(line,case)
        stimulus=(abs(trace['forward_current_a']-case['recovery_forward_a'])
                  <=.12*case['recovery_forward_a'] and
                  abs(trace['peak_reverse_current_a']+case['recovery_reverse_a'])
                  <=.12*case['recovery_reverse_a'])
        checks=dict(forward_voltage=0<forward<=case['forward_max_v'],
                    reverse_leakage=0<=reverse<=case['reverse_max_a'],
                    recovery_stimulus=stimulus,
                    recovery=0<trace['reverse_recovery_s']<=case['recovery_limit_s'])
        rows.append(dict(comparator=case['name'],source=case['source'],
                         conditions={key:value for key,value in case.items()
                                     if key not in ('name','source')},
                         measured=dict(forward_voltage_v=forward,
                                       reverse_leakage_a=reverse),
                         recovery=trace,checks=checks,passed=all(checks.values())))
    capacitance_check=0<cap<=1e-12
    return dict(format='dac-monitor-v21-hv-rectifier-class-check-v1',
                qualification='class-comparator measurements, not V21 factory identity or connected EHT qualification; Rectron recovery return threshold is an explicit proxy',
                model_sha256=hashlib.sha256(MODEL.read_bytes()).hexdigest(),
                capacitance_at_0v_1mhz_f=cap,
                rectron_capacitance_max_f=1e-12,
                capacitance_check=capacitance_check,
                rows=rows,passed=capacitance_check and all(row['passed'] for row in rows))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();report=run()
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    print('V21 class check:', 'pass' if report['passed'] else 'fail')
    return 0 if report['passed'] else 2


if __name__=='__main__':raise SystemExit(main())
