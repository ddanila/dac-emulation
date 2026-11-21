"""Check the live MAA723 functional proxy at documented 723-family bias points.

This is a class comparison, not a claim about the unqualified MAA723 suffix,
the internal transistor circuit, or the connected vertical-stage stress.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent
REGISTER = ROOT/'reference/k7222-11/device-model-register.json'
MODEL_FILE = ROOT/'circuits/k7222-11-vertical-integrator-models.cir'
SHEET = ROOT/'circuits/k7222-11-vertical-integrator.kicad_sch'
PROFILES = [ROOT/'profiles/k7222-11-vertical-integrator.json',
            ROOT/'profiles/k7222-11-vertical-output.json']
SOURCE_ID = '012-6931:A2'
MODEL = 'MAA723_BOUND'
VALUES = re.compile(r'([vi]\([^)]+\))\s*=\s*([+-]?[0-9.]+e[+-][0-9]+)', re.I)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def active_model():
    with tempfile.TemporaryDirectory() as directory:
        xml = Path(directory)/'vertical-integrator.xml'
        subprocess.run(['kicad-cli', 'sch', 'export', 'netlist', '--format',
                        'kicadxml', '-o', str(xml), str(SHEET)],
                       check=True, capture_output=True, text=True)
        components = ET.parse(xml).getroot().findall('./components/comp')
    rows = []
    for component in components:
        source_id = next((field.text for field in component.findall('./fields/field')
                          if field.get('name') == 'SourceId'), None)
        if source_id == SOURCE_ID:
            rows.append((component.get('ref'), component.findtext('value')))
    if len(rows) != 1 or rows[0][1] != MODEL:
        raise ValueError('vertical A2 does not select the checked MAA723 model')
    return rows[0][0]


def registered_parameters():
    register = json.loads(REGISTER.read_text())
    rows = [row for row in register['devices'] if row['id'] == SOURCE_ID]
    if len(rows) != 1 or rows[0]['model'] != MODEL or rows[0]['printed_type'] != 'MAA723':
        raise ValueError('MAA723 register entry is missing or inconsistent')
    parameters = rows[0]['parameters']
    model_text = MODEL_FILE.read_text()
    for name, data in parameters.items():
        if name not in model_text:
            raise ValueError('registered MAA723 parameter is absent from model: '+name)
        for profile_path in PROFILES:
            profile = json.loads(profile_path.read_text())
            actual = profile['parameters'].get(name)
            if actual is None or (actual['nominal'], actual['minimum'], actual['maximum']) != (
                    data['nominal'], *data['bounds']):
                raise ValueError('MAA723 register/profile bounds differ: '+name)
    return register, rows[0]


def op(parameters, *, supply, load_ohm=None, model_file=MODEL_FILE, temperature_c=25):
    values = ' '.join(f'{key}={data["nominal"]:.12g}' for key, data in parameters.items())
    if load_ohm is None:
        circuit = '''Rref ref 0 1T
Rinv inv 0 100k
Rnoninv noninv 0 100k
Rload out 0 1T
Rcomp comp 0 1Meg'''
    else:
        circuit = f'''Rref_top ref noninv 2.15k
Rref_bottom noninv 0 4.99k
Rfeedback out inv 1
Rload out 0 {load_ohm:.12g}
Ccomp comp 0 100p'''
    deck = f'''* 723-family isolated operating point
.param vertical_bf=60 retrace_bf=100 {values}
.include {model_file}
.temp {temperature_c:.12g}
Vvp vp 0 {supply:.12g}
Vvc vc 0 {supply:.12g}
{circuit}
Rcl cl out 1m
Rcs cs out 1m
X723 cs inv noninv ref 0 out vc vp comp cl {MODEL}
.control
op
print v(ref) v(out) i(Vvp) i(Vvc)
quit
.endc
.end
'''
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory)/'check.cir'
        path.write_text(deck)
        result = subprocess.run(['ngspice', '-n', '-b', str(path)],
                                capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError('MAA723 SPICE check failed: '
                           + result.stdout[-700:] + result.stderr[-700:])
    observed = {key.lower(): float(value) for key, value in VALUES.findall(result.stdout)}
    if set(observed) != {'v(ref)', 'v(out)', 'i(vvp)', 'i(vvc)'}:
        raise RuntimeError('MAA723 SPICE values missing: '+result.stdout[-700:])
    return dict(reference_v=observed['v(ref)'], output_v=observed['v(out)'],
                supply_current_a=-observed['i(vvp)']-observed['i(vvc)'])


def run():
    register, entry = registered_parameters()
    parameters = entry['parameters']
    standby = op(parameters, supply=30)
    loads = {name: op(parameters, supply=12, load_ohm=ohm)
             for name, ohm in [('1ma', 5000), ('50ma', 100), ('150ma', 100/3)]}
    targets = entry['comparison_targets']
    checks = {
        'reference_class': targets['reference_v']['range'][0] <= standby['reference_v']
                           <= targets['reference_v']['range'][1],
        'standby_class': 0 < standby['supply_current_a']
                         <= targets['standby_current_a']['maximum'],
        'load_regulation_class': abs(loads['1ma']['output_v']-loads['50ma']['output_v'])
                                 <= targets['load_regulation_v']['maximum'],
        'output_current_capability_proxy': loads['150ma']['output_v']
                                           >= targets['output_150ma_v']['minimum'],
    }
    return dict(format='dac-monitor-maa723-class-check-v1',
                qualification='723-family isolated DC proxy only; exact MAA723 identity, transient response, current limiting and connected-stage stress remain open',
                sources={name: register['sources'][name] for name in entry['sources']},
                register_sha256=sha(REGISTER), model_file_sha256=sha(MODEL_FILE),
                sheet_sha256=sha(SHEET),
                profile_sha256={path.name: sha(path) for path in PROFILES},
                assembly_source_id=SOURCE_ID, assembly_reference=active_model(),
                parameters=parameters, data_book_targets=targets,
                standby_30v=standby, five_volt_loads_12v=loads,
                load_regulation_v=loads['1ma']['output_v']-loads['50ma']['output_v'],
                checks=checks, passed=all(checks.values()))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = run()
    args.output.write_text(json.dumps(report, indent=2)+'\n')
    print(f"MAA723 proxy: reference {report['standby_30v']['reference_v']:.3f} V, "
          f"30 V standby {report['standby_30v']['supply_current_a']*1e3:.3f} mA, "
          f"1–50 mA droop {report['load_regulation_v']*1e3:.3f} mV; "
          f"{'pass' if report['passed'] else 'FAIL'}")
    return 0 if report['passed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
