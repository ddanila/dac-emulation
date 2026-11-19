"""Check live horizontal signal and flyback-rectifier diode class models."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parent
MODEL = ROOT/'circuits/k7222-11-horizontal-models.cir'
RESULT = re.compile(r'([\w()]+)\s*=\s*([-+\d.eE]+)')
CASES = (
    dict(name='HOR_D', ids=['012-6921:V8', '012-6921:V9'],
         printed_type='1AL25', comparator='1N4148',
         source='https://assets.nexperia.com/documents/data-sheet/1N4148_1N4448.pdf',
         forward_current_a=.01, forward_voltage_max_v=1.,
         reverse_voltage_v=20., reverse_current_max_a=25e-9,
         cap_bias_v=0., capacitance_max_f=4e-12,
         recovery_forward_source_v=1.7, recovery_reverse_source_v=-5.5,
         recovery_load_ohm=100., recovery_forward_target_a=.01,
         recovery_reverse_target_a=.06, recovery_return_a=.001,
         recovery_limit_s=4e-9),
    dict(name='HOR_RECT', ids=['012-6921:V14', '012-6921:V15',
                               '012-6921:V16', '012-6921:V17'],
         printed_type='1YL1/2, 1YL1/4, 1YL1/8', comparator='UF4007',
         source='https://www.vishay.com/docs/88755/uf4001.pdf',
         forward_current_a=1., forward_voltage_max_v=1.7,
         reverse_voltage_v=1000., reverse_current_max_a=10e-6,
         cap_bias_v=4., capacitance_typical_f=17e-12,
         recovery_forward_source_v=1.8, recovery_reverse_source_v=-1.6,
         recovery_load_ohm=2., recovery_forward_target_a=.5,
         recovery_reverse_target_a=1., recovery_return_a=.25,
         recovery_limit_s=75e-9),
)
REQUIRED_PARAMETERS = {'IS','N','RS','CJO','TT','BV','IBV'}


def model_line(name, text=None):
    text = MODEL.read_text() if text is None else text
    lines = re.findall(r'^\.model ' + re.escape(name) + r' D\([^\n]*\)$', text, re.M)
    if len(lines) != 1:
        raise ValueError('expected one diode model: '+name)
    line = lines[0]
    if set(re.findall(r'\b([A-Z]+)=',line)) != REQUIRED_PARAMETERS:
        raise ValueError('model has missing or unexpected parameters: '+name)
    return line


def solve(line, source, commands, names):
    deck = '\n'.join(('Horizontal diode class comparison', '.temp 25', line,
                      source, '.control', commands, 'print '+' '.join(names),
                      'quit', '.endc', '.end'))+'\n'
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory)/'diode.cir'
        path.write_text(deck)
        result = subprocess.run(['ngspice','-n','-b',str(path)],
                                capture_output=True,text=True)
    if result.returncode:
        raise RuntimeError('ngspice failed: '+result.stdout[-500:]+result.stderr[-500:])
    values={key:float(value) for key,value in RESULT.findall(result.stdout)}
    if not all(name in values for name in names):
        raise ValueError('missing model measurement: '+result.stdout[-500:])
    return values


def crossing(rows, threshold, direction, start):
    for before,after in zip(rows[start:],rows[start+1:]):
        a,b=before[1],after[1]
        if (a>threshold>=b if direction=='falling' else a<=threshold<b):
            return before[0]+(threshold-a)*(after[0]-before[0])/(b-a)
    raise ValueError('recovery threshold not crossed: '+str(threshold))


def recovery(line, case):
    name=case['name']
    forward=case['recovery_forward_source_v']
    reverse=case['recovery_reverse_source_v']
    load=case['recovery_load_ohm']
    source=(f'VIN src 0 PWL(0 {forward} 10n {forward} 10.05n {reverse} '
            f'200n {reverse})\nRLOAD src a {load}\nVSENSE a b 0\nD1 b 0 {name}')
    with tempfile.TemporaryDirectory() as directory:
        directory=Path(directory)
        trace=directory/'recovery.txt'
        deck=directory/'recovery.cir'
        deck.write_text('\n'.join((
            'Horizontal diode reverse recovery', '.temp 25', line, source,
            '.control', 'tran 0.05n 200n', 'set wr_singlescale',
            'wrdata '+str(trace)+' i(vsense)', 'quit', '.endc', '.end'))+'\n')
        result=subprocess.run(['ngspice','-n','-b',str(deck)],
                              capture_output=True,text=True)
        if result.returncode:
            raise RuntimeError('ngspice recovery failed: '+result.stdout[-500:]+result.stderr[-500:])
        rows=[tuple(map(float,row.split())) for row in trace.read_text().splitlines()]
    if any(len(row)!=2 for row in rows):
        raise ValueError('malformed recovery trace')
    start=next(i for i,(time,_) in enumerate(rows) if time>=10e-9)
    forward_current=rows[start-2][1]
    peak_reverse=min(current for _,current in rows[start:])
    zero=crossing(rows,0.,'falling',start-2)
    return_time=crossing(rows,-case['recovery_return_a'],'rising',start)
    return dict(forward_current_a=forward_current,peak_reverse_current_a=peak_reverse,
                zero_crossing_s=zero,return_to_threshold_s=return_time,
                reverse_recovery_s=return_time-zero,
                return_threshold_a=case['recovery_return_a'],
                series_load_ohm=load,source_transition_s=50e-12,
                sample_step_s=50e-12)


def compare(case, line):
    name=case['name']
    forward=solve(line,f'IF 0 a {case["forward_current_a"]}\nD1 a 0 {name}',
                  'op',['v(a)'])['v(a)']
    reverse=solve(line,f'VR a 0 -{case["reverse_voltage_v"]}\nD1 a 0 {name}',
                  'op',['i(vr)'])['i(vr)']
    cap=solve(line,f'VAC a 0 -{case["cap_bias_v"]} AC 1\nD1 a 0 {name}',
              'ac lin 1 1meg 1meg\nlet cap=-imag(i(vac))/(2*pi*frequency)',
              ['cap'])['cap']
    recovered=recovery(line,case)
    tolerance=.12
    stimulus=(abs(recovered['forward_current_a']-case['recovery_forward_target_a'])
              <=tolerance*case['recovery_forward_target_a'] and
              abs(recovered['peak_reverse_current_a']+case['recovery_reverse_target_a'])
              <=tolerance*case['recovery_reverse_target_a'])
    capacitance_ok=(0<cap<=case['capacitance_max_f'] if 'capacitance_max_f' in case
                    else .5*case['capacitance_typical_f']<=cap<=
                         1.5*case['capacitance_typical_f'])
    checks=dict(forward_voltage=0<forward<=case['forward_voltage_max_v'],
                reverse_current=0<=reverse<=case['reverse_current_max_a'],
                capacitance=capacitance_ok,
                recovery_stimulus=stimulus,
                reverse_recovery=0<recovered['reverse_recovery_s']<=case['recovery_limit_s'])
    return dict(measured=dict(forward_voltage_v=forward,reverse_current_a=reverse,
                              junction_capacitance_f=cap),
                recovery_test=recovered,checks=checks,passed=all(checks.values()))


def run():
    text=MODEL.read_text()
    rows=[]
    for case in CASES:
        line=model_line(case['name'],text)
        rows.append(dict(ids=case['ids'],active_model=case['name'],
                         printed_type=case['printed_type'],comparator=case['comparator'],
                         source=case['source'],conditions={key:value for key,value in case.items()
                             if key not in ('name','ids','printed_type','comparator','source')},
                         comparison=compare(case,line)))
    return dict(format='dac-monitor-horizontal-diode-class-check-v1',
                qualification='provisional current-matched class comparisons; recovery stimulus is an approximate fixture, while original ratings, stage stress and connected sensitivity remain open',
                model_sha256=hashlib.sha256(MODEL.read_bytes()).hexdigest(),
                rows=rows,passed=all(row['comparison']['passed'] for row in rows))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    report=run()
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    print('horizontal diode class checks '+('pass' if report['passed'] else 'fail'))
    return 0 if report['passed'] else 2


if __name__=='__main__':
    raise SystemExit(main())
