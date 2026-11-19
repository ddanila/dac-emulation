"""Check the live vertical 1AE15-class diode against 1N4148 class data.

The 1N4148 is a comparator selected from circuit role, not an original 1AE15
identification. Original ratings and native connected-frame sensitivity remain open.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parent
MODEL = ROOT/'circuits/k7222-11-vertical-integrator-models.cir'
PROFILE = ROOT/'profiles/k7222-11-vertical-output.json'
RESULT = re.compile(r'([\w()]+)\s*=\s*([-+\d.eE]+)')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def model_deck(source, analysis, *, model_name='VERTICAL_DIODE',
               model_file=MODEL, profile_file=PROFILE):
    profile = json.loads(profile_file.read_text())
    parameters = ''.join(f'.param {key}={spec["nominal"]}\n'
                         for key, spec in profile['parameters'].items())
    return (model_name + ' live model check\n.temp 25\n' + parameters
            + model_file.read_text() + '\n' + source + '\n.control\n' + analysis)


def solve(source, analysis, expressions, **model_options):
    deck = (model_deck(source, analysis, **model_options)
            + '\nprint ' + ' '.join(expressions) + '\n.endc\n.end\n')
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory)/'diode.cir'
        path.write_text(deck)
        result = subprocess.run(['ngspice', '-n', '-b', str(path)],
                                capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError('ngspice failed: '+result.stdout[-500:]+result.stderr[-500:])
    values = {name: float(value) for name, value in RESULT.findall(result.stdout)}
    if not all(name in values for name in expressions):
        raise RuntimeError('ngspice omitted requested measurement: '+result.stdout[-500:])
    return values


def crossing(rows, level, direction, start):
    for before, after in zip(rows[start:], rows[start+1:]):
        a, b = before[1], after[1]
        if (a > level >= b if direction == 'falling' else a <= level < b):
            return before[0] + (level-a)*(after[0]-before[0])/(b-a)
    raise RuntimeError('reverse-recovery threshold not crossed: '+str(level))


def recovery(*, forward_source_v=1.7015, **model_options):
    # The 100 ohm series load and step from approximately 10 mA forward to
    # 60 mA reverse follow the comparator's specified test. The source is
    # tuned to these currents for each model; it is not an original-part rating.
    model_name = model_options.get('model_name', 'VERTICAL_DIODE')
    source = (f'VIN src 0 PWL(0 {forward_source_v} 10n {forward_source_v} '
              '10.05n -5.45 30n -5.45)\n'
              'RLOAD src a 100\nVSENSE a b 0\nD1 b 0 ' + model_name)
    with tempfile.TemporaryDirectory() as directory:
        trace = Path(directory)/'recovery.txt'
        deck = Path(directory)/'recovery.cir'
        deck.write_text(model_deck(source, 'tran 0.01n 20n\nset wr_singlescale\n'
                                   + 'wrdata '+str(trace)+' i(vsense)',
                                   **model_options)
                        + '\n.endc\n.end\n')
        result = subprocess.run(['ngspice', '-n', '-b', str(deck)],
                                capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError('ngspice recovery check failed: '
                               +result.stdout[-500:]+result.stderr[-500:])
        rows = [tuple(map(float, line.split())) for line in trace.read_text().splitlines()]
    if not rows or any(len(row) != 2 for row in rows):
        raise RuntimeError('missing or malformed reverse-recovery trace')
    step_start = next(i for i, (time, _) in enumerate(rows) if time >= 10e-9)
    if step_start < 2:
        raise RuntimeError('reverse-recovery forward interval missing')
    forward_current = rows[step_start-2][1]
    reverse_peak = min(row[1] for row in rows[step_start:])
    zero = crossing(rows, 0, 'falling', step_start-2)
    return_1ma = crossing(rows, -1e-3, 'rising', step_start)
    return dict(forward_current_a=forward_current,
                peak_reverse_current_a=reverse_peak,
                zero_crossing_s=zero,
                return_to_1ma_s=return_1ma,
                reverse_recovery_s=return_1ma-zero,
                series_load_ohm=100,
                source_transition_s=5e-11,
                sample_step_s=1e-11)


def run(*, model_name='VERTICAL_DIODE', model_file=MODEL, profile_file=PROFILE,
        recovery_forward_source_v=1.7015):
    options = dict(model_name=model_name, model_file=model_file,
                   profile_file=profile_file)
    forward = solve(f'IF 0 a 10m\nD1 a 0 {model_name}', 'op', ('v(a)',),
                    **options)['v(a)']
    reverse = solve(f'VR a 0 -20\nD1 a 0 {model_name}',
                    'op', ('i(vr)',), **options)['i(vr)']
    capacitance = solve(f'VAC a 0 0 AC 1\nD1 a 0 {model_name}',
                        'ac lin 1 1meg 1meg\nlet cap=-imag(i(vac))/(2*pi*frequency)',
                        ('cap',), **options)['cap']
    recovery_result = recovery(forward_source_v=recovery_forward_source_v,
                               **options)
    recovery_conditions_met = (abs(recovery_result['forward_current_a']-0.01) <= 0.0005
                               and abs(recovery_result['peak_reverse_current_a']+0.06) <= 0.003
                               and recovery_result['series_load_ohm'] == 100)
    return dict(format='dac-monitor-1ae15-class-model-check-v2',
                qualification='provisional 1N4148-class comparison; original 1AE15 identity and native connected-frame sensitivity remain open',
                comparator='https://assets.nexperia.com/documents/data-sheet/1N4148_1N4448.pdf',
                model_sha256=sha(model_file), profile_sha256=sha(profile_file),
                measured=dict(forward_voltage_v_at_10ma=forward,
                              reverse_current_a_at_20v=reverse,
                              zero_bias_capacitance_f_at_1mhz=capacitance),
                comparator_maxima=dict(forward_voltage_v_at_10ma=1,
                                       reverse_current_a_at_20v=2.5e-8,
                                       zero_bias_capacitance_f_at_1mhz=4e-12,
                                       reverse_recovery_s_at_specified_test=4e-9),
                checked=dict(forward_voltage=0<forward<=1,
                             reverse_current=0<=reverse<=2.5e-8,
                             zero_bias_capacitance=0<capacitance<=4e-12,
                             reverse_recovery=(recovery_conditions_met and
                                               0<recovery_result['reverse_recovery_s']<=4e-9)),
                recovery_test=recovery_result,
                unchecked=['original 1AE15 identity and operating ratings',
                           'joint-bound and native connected-frame response'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = run()
    args.output.write_text(json.dumps(report, indent=2)+'\n')
    print('forward/reverse/capacitance/recovery comparator checks:',
          'pass' if all(report['checked'].values()) else 'fail')
    return 0 if all(report['checked'].values()) else 2


if __name__ == '__main__':
    raise SystemExit(main())
