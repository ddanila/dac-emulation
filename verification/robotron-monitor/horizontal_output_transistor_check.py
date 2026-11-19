"""Compare the live V18 SPICE model with BU508AF-class DC data-sheet biases.

This checks gain and a current-fed DC saturation proxy. Inductive storage,
fall time, thermal stress and safe operating area remain unverified.
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
MODELS = ROOT/'circuits/k7222-11-horizontal-models.cir'
SHEET = ROOT/'circuits/k7222-11-horizontal-output.kicad_sch'
SOURCE = 'https://www.st.com/resource/en/datasheet/bu508af.pdf'
VALUE = re.compile(r'(i\(vce\)|v\(c\)|v\(b\))\s*=\s*([-+\d.eE]+)')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def op(stimulus, probes):
    deck = ('V18 horizontal-output DC proxy\n.temp 25\n' + MODELS.read_text()
            + '\nQ1 c b 0 HOR_OUTPUT_N\n' + stimulus
            + '.control\nop\nprint ' + ' '.join(probes) + '\n.endc\n.end\n')
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory)/'bias.cir'
        path.write_text(deck)
        result = subprocess.run(['ngspice', '-n', '-b', str(path)],
                                capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError('ngspice V18 bias check failed: '+result.stdout[-500:]+result.stderr[-500:])
    values = {key: float(value) for key, value in VALUE.findall(result.stdout)}
    if set(values) != set(probes):
        raise RuntimeError('ngspice omitted V18 bias values: '+result.stdout[-500:])
    return values


def gain_at(collector_target_a):
    low, high = 1e-6, 1.0
    for _ in range(24):
        base_a = (low+high)/2
        point = op(f'VCE c 0 5\nIBASE 0 b {base_a:.12g}\n',
                   ('i(vce)', 'v(b)'))
        if -point['i(vce)'] > collector_target_a:
            high = base_a
        else:
            low = base_a
    base_a = (low+high)/2
    point = op(f'VCE c 0 5\nIBASE 0 b {base_a:.12g}\n',
               ('i(vce)', 'v(b)'))
    collector_a = -point['i(vce)']
    return dict(collector_current_a=collector_a, base_current_a=base_a,
                collector_emitter_voltage_v=5, base_emitter_voltage_v=point['v(b)'],
                hFE=collector_a/base_a)


def active_model():
    with tempfile.TemporaryDirectory() as directory:
        xml = Path(directory)/'output.xml'
        subprocess.run(['kicad-cli', 'sch', 'export', 'netlist', '--format', 'kicadxml',
                        '-o', str(xml), str(SHEET)], check=True,
                       capture_output=True, text=True)
        root = ET.parse(xml).getroot()
    rows = []
    for comp in root.findall('./components/comp'):
        source_id = next((field.text for field in comp.findall('./fields/field')
                          if field.get('name') == 'SourceId'), None)
        if source_id == '012-6921:V18':
            rows.append((comp.get('ref'), comp.findtext('value')))
    if len(rows) != 1 or rows[0][1] != 'HOR_OUTPUT_N':
        raise ValueError('V18 KiCad export does not select the tested model')
    return rows[0][0]


def run():
    register = json.loads(REGISTER.read_text())
    matches = [device for device in register['devices'] if device['id'] == '012-6921:V18']
    if len(matches) != 1 or matches[0]['model'] != 'HOR_OUTPUT_N':
        raise ValueError('V18 device register is missing or inconsistent')
    targets = matches[0]['comparison_targets']
    low = gain_at(.1)
    high = gain_at(4.5)
    sat = op('ICLOAD 0 c 4.5\nIBASE 0 b 1.6\n', ('v(c)', 'v(b)'))
    results = {
        'hFE_0p1a': 10 <= low['hFE'] <= 30 and abs(low['collector_current_a']-.1) < .001,
        'hFE_4p5a': high['hFE'] >= 5 and abs(high['collector_current_a']-4.5) < .045,
        'VCEsat_dc_proxy': 0 <= sat['v(c)'] <= 1,
    }
    if (targets['hFE_0p1a']['minimum'], targets['hFE_0p1a']['maximum'],
            targets['hFE_4p5a']['minimum'], targets['VCEsat_v']['maximum']) != (10, 30, 5, 1):
        raise ValueError('V18 data-sheet target changed without updating comparison')
    return dict(format='dac-monitor-v18-model-dc-check-v1',
                qualification='BU508AF-class DC proxy only; inductive switching and connected-stage SOA remain open',
                source=SOURCE, model_file_sha256=sha(MODELS),
                register_sha256=sha(REGISTER), sheet_sha256=sha(SHEET),
                assembly_source_id='012-6921:V18', assembly_reference=active_model(),
                data_sheet_targets=targets,
                low_current_gain=low, operating_current_gain=high,
                saturation_dc_proxy=dict(collector_current_a=4.5,
                                         base_current_a=1.6,
                                         collector_emitter_voltage_v=sat['v(c)'],
                                         base_emitter_voltage_v=sat['v(b)']),
                checks=results, passed=all(results.values()))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = run()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2)+'\n')
    print(f"V18 hFE {report['low_current_gain']['hFE']:.2f} at 0.1 A, "
          f"{report['operating_current_gain']['hFE']:.2f} at 4.5 A; "
          f"DC VCEsat proxy {report['saturation_dc_proxy']['collector_emitter_voltage_v']:.3f} V")
    return 0 if report['passed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
