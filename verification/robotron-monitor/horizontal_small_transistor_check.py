"""Check the active V10 and V12 models at historical data-book bias points.

SC237E has a documented gain group. The printed SF1260 suffix is unresolved,
so its gain check covers only the SF126–129 base-family range.
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
MODELS = ROOT/'circuits/k7222-11-horizontal-models.cir'
SHEET = ROOT/'circuits/k7222-11-horizontal-oscillator.kicad_sch'
SOURCE = 'https://www.tiffe.de/Robotron/Bausteinuebersicht/DDR-Halbleiter.pdf'
SPECS = {
    '012-6921:V10': dict(model='SC237E_N', target_ic=.002, target_vce=6,
                         ac_ic=.01, ac_vce=6, ac_hz=20e6,
                         sat_ic=.1, sat_ib=.005),
    '012-6921:V12': dict(model='HOR_N', target_ic=.05, target_vce=2,
                         ac_ic=.01, ac_vce=10, ac_hz=15e6,
                         sat_ic=.15, sat_ib=.015),
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def active_models():
    with tempfile.TemporaryDirectory() as directory:
        xml = Path(directory)/'oscillator.xml'
        subprocess.run(['kicad-cli', 'sch', 'export', 'netlist',
                        '--format', 'kicadxml', '-o', str(xml), str(SHEET)],
                       check=True, capture_output=True, text=True)
        root = ET.parse(xml).getroot()
    rows = {}
    for comp in root.findall('./components/comp'):
        source_id = next((field.text for field in comp.findall('./fields/field')
                          if field.get('name') == 'SourceId'), None)
        if source_id in SPECS:
            if source_id in rows:
                raise ValueError('duplicate KiCad transistor '+source_id)
            rows[source_id] = dict(reference=comp.get('ref'), model=comp.findtext('value'))
    if set(rows) != set(SPECS):
        raise ValueError('V10/V12 missing from KiCad export')
    for source_id, spec in SPECS.items():
        if rows[source_id]['model'] != spec['model']:
            raise ValueError(source_id+' KiCad export selects a different model')
    return rows


def model_tokens(name):
    match = re.search(r'^\.model ' + name + r' NPN\(([^)]*)\)', MODELS.read_text(), re.M)
    if not match:
        raise ValueError('missing active model '+name)
    return dict(re.findall(r'([A-Z]+)=([^\s]+)', match.group(1)))


def numeric(token):
    scales = {'p': 1e-12, 'n': 1e-9, 'u': 1e-6}
    scale = scales.get(token[-1], 1)
    return float(token[:-1] if scale != 1 else token)*scale


def check_one(source_id, spec, entry, active):
    model = spec['model']
    if entry['model'] != model:
        raise ValueError(source_id+' register model differs from KiCad')
    tokens = model_tokens(model)
    if set(tokens) != set(entry['parameters']):
        raise ValueError(source_id+' register lacks an explicit model parameter')
    for key, token in tokens.items():
        if abs(numeric(token)-entry['parameters'][key]['nominal']) > 1e-9*max(abs(numeric(token)), 1e-15):
            raise ValueError(source_id+' register nominal differs from live '+key)
    gain = bench.gain_at(spec['target_ic'], spec['target_vce'], model)
    bias = bench.gain_at(spec['ac_ic'], spec['ac_vce'], model)
    ac_gain = bench.ac_gain_at(bias['base_current_a'], spec['ac_vce'], spec['ac_hz'], model)
    ft_proxy = spec['ac_hz']*ac_gain
    sat = bench.op(f"ICLOAD 0 c {spec['sat_ic']}\nIBASE 0 b {spec['sat_ib']}",
                   ('v(c)', 'v(b)'), model)
    targets = entry['comparison_targets']
    if source_id.endswith('V10'):
        if (targets['hFE']['range'], targets['VCEsat_v']['typical'],
                targets['fT_hz']['typical']) != ([224, 560], .21, 170e6):
            raise ValueError('SC237E source targets changed without updating check')
        checks = dict(group_e_gain=224 <= gain['hFE'] <= 560,
                      typical_saturation_proximity=abs(sat['v(c)']-.21) <= .105,
                      typical_transition_frequency_proximity=abs(ft_proxy-170e6) <= 51e6)
    else:
        if (targets['hFE']['range'], targets['VCEsat_v']['maximum'],
                targets['fT_hz']['minimum']) != ([18, 1120], .5, 60e6):
            raise ValueError('SF126 family source targets changed without updating check')
        checks = dict(broad_family_gain=18 <= gain['hFE'] <= 1120,
                      saturation_dc_proxy=0 <= sat['v(c)'] <= .5,
                      transition_frequency_proxy=ft_proxy >= 60e6)
    checks['gain_bias_reached'] = abs(gain['collector_current_a']-spec['target_ic']) < .01*spec['target_ic']
    checks['ac_bias_reached'] = abs(bias['collector_current_a']-spec['ac_ic']) < .01*spec['ac_ic']
    return dict(source_id=source_id, assembly_reference=active['reference'],
                active_model=model, explicit_model_parameters=tokens,
                data_book_targets=targets, gain_bias=gain,
                saturation_dc_proxy=dict(collector_current_a=spec['sat_ic'],
                                         base_current_a=spec['sat_ib'],
                                         collector_emitter_voltage_v=sat['v(c)'],
                                         base_emitter_voltage_v=sat['v(b)']),
                ac_bias=bias, ac_test_frequency_hz=spec['ac_hz'],
                ac_current_gain=ac_gain, transition_frequency_proxy_hz=ft_proxy,
                checks=checks, passed=all(checks.values()))


def run():
    register = json.loads(REGISTER.read_text())
    entries = {row['id']: row for row in register['devices'] if row['id'] in SPECS}
    if set(entries) != set(SPECS):
        raise ValueError('V10/V12 device register is incomplete')
    active = active_models()
    rows = [check_one(source_id, spec, entries[source_id], active[source_id])
            for source_id, spec in SPECS.items()]
    return dict(format='dac-monitor-v10-v12-model-class-check-v1',
                qualification='historical transistor-family DC/AC proxies; SF1260 suffix, '
                              'connected stress and implicit SPICE defaults remain open',
                source=SOURCE, model_file_sha256=sha(MODELS),
                register_sha256=sha(REGISTER), sheet_sha256=sha(SHEET),
                devices=rows, passed=all(row['passed'] for row in rows))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = run()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2)+'\n')
    for row in report['devices']:
        print(f"{row['source_id']}: hFE {row['gain_bias']['hFE']:.1f}, "
              f"VCEsat {row['saturation_dc_proxy']['collector_emitter_voltage_v']:.3f} V, "
              f"fT proxy {row['transition_frequency_proxy_hz']/1e6:.1f} MHz")
    return 0 if report['passed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
