"""Compare the live 5.1 V reference zener model with a documented class device."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parent
MODEL = ROOT/'circuits/k7222-11-regulator5-models.cir'
SOURCE = ROOT/'reference/k7222-11/page9-reference-source-netlist.json'
COMPARATOR = 'https://assets.nexperia.com/documents/data-sheet/BZX84_SER.pdf'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def model_line(text):
    lines = re.findall(r'^\.model REG5_ZENER D\([^\n]*\)$', text, re.M)
    if len(lines) != 1:
        raise ValueError('expected one REG5_ZENER diode model')
    return lines[0]


def voltage_at_current(line, current):
    if not 0 < current <= .02:
        raise ValueError('invalid reverse test current')
    with tempfile.TemporaryDirectory() as directory:
        deck = Path(directory)/'zener.cir'
        deck.write_text('\n'.join([
            '5.1 V zener reverse-bias comparison', line,
            f'Itest 0 cathode {current:.9g}', 'Dtest 0 cathode REG5_ZENER',
            '.options tnom=25', '.temp 25',
            '.control', 'op', 'print v(cathode)', 'quit', '.endc', '.end',
        ])+'\n')
        result = subprocess.run(['ngspice', '-b', str(deck)], capture_output=True,
                                text=True, check=True)
    found = re.search(r'v\(cathode\)\s*=\s*([+-]?[0-9.]+e[+-][0-9]+)',
                      result.stdout, re.I)
    if not found:
        raise ValueError('ngspice did not report the zener voltage')
    return float(found.group(1))


def compare(line):
    # BZX84-C5V1 at 25 C: Vz 4.8–5.4 V and rdif <=60 ohm at Iz=5 mA.
    currents = (.0049, .005, .0051)
    values = [voltage_at_current(line, current) for current in currents]
    resistance = (values[2]-values[0])/(currents[2]-currents[0])
    checks = {'voltage_at_5ma': 4.8 <= values[1] <= 5.4,
              'differential_resistance_near_5ma': 0 < resistance <= 60}
    return dict(currents_a=list(currents), reverse_voltages_v=values,
                differential_resistance_ohm=resistance, checks=checks,
                passed=all(checks.values()))


def run():
    source = json.loads(SOURCE.read_text())
    if source['diode_directions'] != [dict(part='V3', anode_net='0', cathode_net='ZENER_REF')]:
        raise ValueError('page-9 source zener orientation changed')
    measurement = compare(model_line(MODEL.read_text()))
    return dict(format='dac-monitor-regulator5-zener-model-check-v1',
                qualification='BZX84-C5V1 class comparison at 25 C; original ZC5.1 identity, stage stress and other model parameters remain open',
                source_read_sha256=sha(SOURCE), model_sha256=sha(MODEL),
                comparator=COMPARATOR,
                comparator_conditions=dict(test_current_a=.005,
                                           zener_voltage_range_v=[4.8, 5.4],
                                           maximum_differential_resistance_ohm=60),
                measurement=measurement)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = run()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2)+'\n')
    print('5.1 V zener class comparison '+('passes' if report['measurement']['passed'] else 'fails'))
    return 0 if report['measurement']['passed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
