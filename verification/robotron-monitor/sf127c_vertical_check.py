"""Check the live vertical V18 SF127C NPN against the historical group-C sheet."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import tempfile
import xml.etree.ElementTree as ET

import horizontal_driver_transistor_check as transistor

ROOT = Path(__file__).resolve().parent
REGISTER = ROOT/'reference/k7222-11/device-model-register.json'
MODELS = ROOT/'circuits/k7222-11-vertical-integrator-models.cir'
SHEET = ROOT/'circuits/k7222-11-vertical-output.kicad_sch'
SOURCE_ID = '012-6931:V18'
MODEL = 'SF127C_N'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def active_model():
    with tempfile.TemporaryDirectory() as directory:
        xml = Path(directory)/'vertical-output.xml'
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
        raise ValueError('vertical V18 does not select the checked SF127C model')
    return rows[0][0]


def model_line(entry):
    match = re.search(r'^\.model '+MODEL+r' NPN\(([^)]*)\)', MODELS.read_text(), re.M)
    if not match:
        raise ValueError('SF127C model declaration is absent')
    tokens = dict(re.findall(r'([A-Z]+)=([^\s]+)', match.group(1)))
    if set(tokens) != set(entry['parameters']):
        raise ValueError('SF127C register does not cover every explicit model parameter')
    scales = {'p': 1e-12, 'n': 1e-9, 'u': 1e-6}
    for key, token in tokens.items():
        scale = scales.get(token[-1], 1)
        numeric = float(token[:-1] if scale != 1 else token)*scale
        if not math.isclose(numeric, entry['parameters'][key]['nominal'], rel_tol=1e-10):
            raise ValueError('SF127C register differs from live '+key)
    return tokens, match.group(0)


def run():
    register = json.loads(REGISTER.read_text())
    matches = [row for row in register['devices'] if row['id'] == SOURCE_ID]
    if len(matches) != 1 or matches[0]['model'] != MODEL or matches[0]['printed_type'] != 'SF127C':
        raise ValueError('SF127C device register is missing or inconsistent')
    entry = matches[0]
    tokens, line = model_line(entry)
    with tempfile.TemporaryDirectory() as directory:
        model_path = Path(directory)/'sf127c.cir'
        model_path.write_text(line+'\n')
        gain = transistor.gain_at(.05, 2, model=MODEL, models_path=model_path)
        ac_bias = transistor.gain_at(.01, 10, model=MODEL, models_path=model_path)
        ac_gain = transistor.ac_gain_at(ac_bias['base_current_a'], 10, 15e6,
                                       model=MODEL, models_path=model_path)
        saturation = transistor.op('ICLOAD 0 c .15\nIBASE 0 b .015',
                                   ('v(c)', 'v(b)'), model=MODEL, models_path=model_path)
    targets = entry['comparison_targets']
    checks = dict(
        group_c_gain=targets['hFE_50ma']['range'][0] <= gain['hFE'] <= targets['hFE_50ma']['range'][1]
            and abs(gain['collector_current_a']-.05) < .0005,
        saturation_dc_proxy=0 <= saturation['v(c)'] <= targets['VCEsat_v']['maximum'],
        transition_frequency_proxy=15e6*ac_gain >= targets['fT_hz']['minimum']
            and abs(ac_bias['collector_current_a']-.01) < .0001,
    )
    return dict(format='dac-monitor-sf127c-vertical-class-check-v1',
                qualification='original SF127 group-C class response at catalog points; connected stress, joint bounds and implicit defaults remain open',
                source=register['sources']['ddr_sf126_129'],
                register_sha256=sha(REGISTER), model_file_sha256=sha(MODELS),
                sheet_sha256=sha(SHEET), assembly_source_id=SOURCE_ID,
                assembly_reference=active_model(), explicit_model_parameters=tokens,
                data_book_targets=targets, gain_at_50ma=gain,
                saturation_dc_proxy=dict(collector_current_a=.15, base_current_a=.015,
                                         collector_emitter_voltage_v=saturation['v(c)'],
                                         base_emitter_voltage_v=saturation['v(b)']),
                ac_bias_at_10ma=ac_bias, ac_current_gain_at_15mhz=ac_gain,
                transition_frequency_proxy_hz=15e6*ac_gain,
                checks=checks, passed=all(checks.values()))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = run()
    args.output.write_text(json.dumps(report, indent=2)+'\n')
    print(f"SF127C hFE {report['gain_at_50ma']['hFE']:.1f}; "
          f"DC VCEsat {report['saturation_dc_proxy']['collector_emitter_voltage_v']:.3f} V; "
          f"15 MHz fT proxy {report['transition_frequency_proxy_hz']/1e6:.1f} MHz")
    return 0 if report['passed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
