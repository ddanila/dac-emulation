"""Compare the page-9 V4 regulator transistor with the SF126 base family.

The source parts list prints SF1260. The available historical data book does
not identify that suffix, so its gain check uses the full family A–F range.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile
import xml.etree.ElementTree as ET

import horizontal_driver_transistor_check as bench

ROOT = Path(__file__).resolve().parent
REGISTER = ROOT/'reference/k7222-11/device-model-register.json'
PROFILE = ROOT/'profiles/k7222-11-regulator5.json'
MODELS = ROOT/'circuits/k7222-11-regulator5-models.cir'
SHEET = ROOT/'circuits/k7222-11-regulator5.kicad_sch'
SOURCE = 'https://www.tiffe.de/Robotron/Bausteinuebersicht/DDR-Halbleiter.pdf'
SOURCE_ID = '012-6931:V4'
MODEL = 'REG5_NPN'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def active_model():
    with tempfile.TemporaryDirectory() as directory:
        xml = Path(directory)/'regulator5.xml'
        subprocess.run(['kicad-cli', 'sch', 'export', 'netlist', '--format',
                        'kicadxml', '-o', str(xml), str(SHEET)], check=True,
                       capture_output=True, text=True)
        root = ET.parse(xml).getroot()
    rows = []
    for comp in root.findall('./components/comp'):
        source_id = next((field.text for field in comp.findall('./fields/field')
                          if field.get('name') == 'SourceId'), None)
        if source_id == SOURCE_ID:
            rows.append((comp.get('ref'), comp.findtext('value')))
    if len(rows) != 1 or rows[0][1] != MODEL:
        raise ValueError('page-9 V4 KiCad export does not select REG5_NPN')
    return rows[0][0]


def run():
    register = json.loads(REGISTER.read_text())
    rows = [row for row in register['devices'] if row['id'] == SOURCE_ID]
    if len(rows) != 1 or rows[0]['model'] != MODEL:
        raise ValueError('page-9 V4 device register is missing or inconsistent')
    entry = rows[0]
    profile = json.loads(PROFILE.read_text())
    bf = profile['parameters']['reg5_bf']
    if (bf['nominal'], [bf['minimum'], bf['maximum']]) != (
            entry['parameters']['BF']['nominal'], entry['parameters']['BF']['bounds']):
        raise ValueError('V4 gain bounds differ from active profile')
    match = re.search(r'^\.model REG5_NPN NPN\(([^)]*)\)', MODELS.read_text(), re.M)
    if not match:
        raise ValueError('active REG5_NPN declaration missing')
    tokens = dict(re.findall(r'([A-Z]+)=([^\s]+)', match.group(1)))
    if set(tokens) != set(entry['parameters']) or tokens['BF'] != '{reg5_bf}':
        raise ValueError('V4 register does not cover the live parameter set')
    scales = {'p': 1e-12, 'n': 1e-9, 'u': 1e-6}
    for key, token in tokens.items():
        if key == 'BF':
            continue
        scale = scales.get(token[-1], 1)
        numeric = float(token[:-1] if scale != 1 else token)*scale
        if abs(numeric-entry['parameters'][key]['nominal']) > 1e-9*max(abs(numeric), 1e-15):
            raise ValueError('V4 register nominal differs from live '+key)
    with tempfile.TemporaryDirectory() as directory:
        resolved = Path(directory)/'regulator5-resolved.cir'
        resolved.write_text(MODELS.read_text().replace('{reg5_bf}', str(bf['nominal'])))
        gain = bench.gain_at(.05, 2, MODEL, resolved)
        ac_bias = bench.gain_at(.01, 10, MODEL, resolved)
        ac_gain = bench.ac_gain_at(ac_bias['base_current_a'], 10, 15e6, MODEL, resolved)
        sat = bench.op('ICLOAD 0 c .15\nIBASE 0 b .015', ('v(c)', 'v(b)'), MODEL, resolved)
    ft_proxy = 15e6*ac_gain
    targets = entry['comparison_targets']
    if (targets['hFE_50ma']['range'], targets['VCEsat_v']['maximum'],
            targets['fT_hz']['minimum']) != ([18, 1120], .5, 60e6):
        raise ValueError('SF126 family targets changed without updating comparison')
    checks = dict(broad_family_gain=18 <= gain['hFE'] <= 1120
                  and abs(gain['collector_current_a']-.05) < .0005,
                  saturation_dc_proxy=0 <= sat['v(c)'] <= .5,
                  transition_frequency_proxy=ft_proxy >= 60e6
                  and abs(ac_bias['collector_current_a']-.01) < .0001)
    return dict(format='dac-monitor-regulator5-transistor-class-check-v1',
                qualification='SF126 base-family DC and 15 MHz AC proxies; SF1260 suffix, '
                              'joint bounds and connected stress remain open',
                source=SOURCE, model_file_sha256=sha(MODELS),
                profile_sha256=sha(PROFILE), register_sha256=sha(REGISTER),
                sheet_sha256=sha(SHEET), assembly_source_id=SOURCE_ID,
                assembly_reference=active_model(),
                explicit_model_parameters=tokens, resolved_bf=bf['nominal'],
                data_book_targets=targets, gain_at_50ma=gain,
                saturation_dc_proxy=dict(collector_current_a=.15,
                                         base_current_a=.015,
                                         collector_emitter_voltage_v=sat['v(c)'],
                                         base_emitter_voltage_v=sat['v(b)']),
                ac_bias_at_10ma=ac_bias, ac_current_gain_at_15mhz=ac_gain,
                transition_frequency_proxy_hz=ft_proxy,
                checks=checks, passed=all(checks.values()))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = run()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2)+'\n')
    print(f"V4 hFE {report['gain_at_50ma']['hFE']:.1f}; "
          f"DC VCEsat {report['saturation_dc_proxy']['collector_emitter_voltage_v']:.3f} V; "
          f"15 MHz fT proxy {report['transition_frequency_proxy_hz']/1e6:.1f} MHz")
    return 0 if report['passed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
