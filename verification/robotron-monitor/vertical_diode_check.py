"""Check the live vertical 1AE15-class diode against 1N4148 class DC data.

The 1N4148 is a comparator selected from circuit role, not an original 1AE15
identification. Reverse recovery and stage sensitivity remain open.
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


def solve(source, analysis, expressions):
    profile = json.loads(PROFILE.read_text())
    parameters = ''.join(f'.param {key}={spec["nominal"]}\n'
                         for key, spec in profile['parameters'].items())
    deck = ('VERTICAL_DIODE live model check\n.temp 25\n' + parameters
            + MODEL.read_text() + '\n' + source + '\n.control\n' + analysis
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


def run():
    forward = solve('IF 0 a 10m\nD1 a 0 VERTICAL_DIODE', 'op', ('v(a)',))['v(a)']
    reverse = solve('VR a 0 -20\nD1 a 0 VERTICAL_DIODE',
                    'op', ('i(vr)',))['i(vr)']
    capacitance = solve('VAC a 0 0 AC 1\nD1 a 0 VERTICAL_DIODE',
                        'ac lin 1 1meg 1meg\nlet cap=-imag(i(vac))/(2*pi*frequency)',
                        ('cap',))['cap']
    return dict(format='dac-monitor-1ae15-class-dc-check-v1',
                qualification='provisional 1N4148-class comparison; 1AE15 identity, reverse recovery and stage sensitivity remain open',
                comparator='https://assets.nexperia.com/documents/data-sheet/1N4148_1N4448.pdf',
                model_sha256=sha(MODEL), profile_sha256=sha(PROFILE),
                measured=dict(forward_voltage_v_at_10ma=forward,
                              reverse_current_a_at_20v=reverse,
                              zero_bias_capacitance_f_at_1mhz=capacitance),
                comparator_maxima=dict(forward_voltage_v_at_10ma=1,
                                       reverse_current_a_at_20v=2.5e-8,
                                       zero_bias_capacitance_f_at_1mhz=4e-12,
                                       reverse_recovery_s_at_specified_test=4e-9),
                checked=dict(forward_voltage=0<forward<=1,
                             reverse_current=0<=reverse<=2.5e-8,
                             zero_bias_capacitance=0<capacitance<=4e-12),
                unchecked=['reverse recovery at data-sheet IF/IR/RL',
                           'original 1AE15 identity and operating ratings',
                           'stage response across registered parameter bounds'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = run()
    args.output.write_text(json.dumps(report, indent=2)+'\n')
    print('forward/reverse/capacitance comparator checks:',
          'pass' if all(report['checked'].values()) else 'fail')
    return 0 if all(report['checked'].values()) else 2


if __name__ == '__main__':
    raise SystemExit(main())
