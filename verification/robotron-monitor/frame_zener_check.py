"""Compare the three unregistered frame-path zeners with BZX84 class limits.

The comparison checks the live SPICE model at the data-sheet test current. It
does not establish the historical part identity or connected-stage stress.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parent
COMPARATOR = 'https://assets.nexperia.com/documents/data-sheet/BZX84_SER.pdf'
CASES = (
    ('012-6921:V4', 'Z9_BOUND', 'circuits/signal-path-models.cir', 'BZX84-C9V1', (8.5, 9.6), 15),
    ('012-6921:V11', 'HOR_Z6', 'circuits/k7222-11-horizontal-models.cir', 'BZX84-C6V2', (5.8, 6.6), 10),
    ('012-6931:V15', 'VERT_Z16', 'circuits/k7222-11-vertical-output-models.cir', 'BZX84-C16', (15.3, 17.1), 40),
)
REQUIRED_PARAMETERS = {'IS', 'N', 'RS', 'BV', 'IBV', 'CJO', 'TT'}
EXPLICIT_HORIZONTAL_DEFAULTS = {'VJ', 'M', 'FC', 'EG', 'XTI'}


def model_line(path, name):
    lines = re.findall(r'^\.model ' + re.escape(name) + r' D\([^\n]*\)$',
                       path.read_text(), re.M)
    if len(lines) != 1:
        raise ValueError('expected one diode model for ' + name)
    line = lines[0]
    keys = set(re.findall(r'\b([A-Z]+)=', line))
    expected = REQUIRED_PARAMETERS | (EXPLICIT_HORIZONTAL_DEFAULTS if name == 'HOR_Z6' else set())
    if keys != expected:
        raise ValueError(name + ' has missing or unexpected parameters: ' + str(keys))
    return line


def voltage_at_current(line, name, current):
    with tempfile.TemporaryDirectory() as directory:
        deck = Path(directory)/'zener.cir'
        deck.write_text('\n'.join((
            'Frame zener class comparison', line,
            f'Itest 0 cathode {current:.9g}', f'Dtest 0 cathode {name}',
            '.options tnom=25', '.temp 25',
            '.control', 'op', 'print v(cathode)', 'quit', '.endc', '.end',
        ))+'\n')
        result = subprocess.run(['ngspice', '-b', str(deck)], capture_output=True,
                                text=True, check=True)
    match = re.search(r'v\(cathode\)\s*=\s*([+-]?[0-9.]+e[+-][0-9]+)',
                      result.stdout, re.I)
    if not match:
        raise ValueError('ngspice did not report the zener voltage for ' + name)
    return float(match.group(1))


def compare(line, name, voltage_range, maximum_resistance):
    currents = (.0049, .005, .0051)
    voltages = [voltage_at_current(line, name, current) for current in currents]
    resistance = (voltages[2]-voltages[0])/(currents[2]-currents[0])
    checks = dict(voltage_at_5ma=voltage_range[0] <= voltages[1] <= voltage_range[1],
                  differential_resistance_near_5ma=0 < resistance <= maximum_resistance)
    return dict(currents_a=list(currents), reverse_voltages_v=voltages,
                differential_resistance_ohm=resistance, checks=checks,
                passed=all(checks.values()))


def run():
    rows = []
    for part, name, relative_path, comparator, voltage_range, resistance_limit in CASES:
        path = ROOT/relative_path
        line = model_line(path, name)
        rows.append(dict(id=part, active_model=name, model_file=relative_path,
                         model_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                         comparator=comparator,
                         comparator_conditions=dict(temperature_c=25, current_a=.005,
                             voltage_range_v=list(voltage_range),
                             maximum_differential_resistance_ohm=resistance_limit),
                         measurement=compare(line, name, voltage_range, resistance_limit)))
    return dict(format='dac-monitor-frame-zener-class-check-v1',
                qualification='class comparison only; original identity, stage stress and bounded sensitivity remain open',
                source=COMPARATOR, source_revision='Rev. 7, 1 January 2023',
                rows=rows, passed=all(row['measurement']['passed'] for row in rows))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = run()
    args.output.write_text(json.dumps(report, indent=2)+'\n')
    print('frame zener class comparison ' + ('passes' if report['passed'] else 'fails'))
    return 0 if report['passed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
