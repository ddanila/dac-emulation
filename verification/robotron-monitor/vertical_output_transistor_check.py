"""Compare the provisional V27/V28 output BJTs with BD139/BD140 class data."""
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
PROFILE = ROOT/'profiles/k7222-11-vertical-output.json'
MODELS = ROOT/'circuits/k7222-11-vertical-output-models.cir'
SHEET = ROOT/'circuits/k7222-11-vertical-output.kicad_sch'
SPECS = {
    '012-6931:V27': ('VERT_POWER_N', False, 'output_n_tf', 250e6),
    '012-6931:V28': ('VERT_POWER_P', True, 'output_p_tf', 75e6),
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def active_models():
    with tempfile.TemporaryDirectory() as directory:
        exported = Path(directory)/'output.xml'
        subprocess.run(['kicad-cli', 'sch', 'export', 'netlist', '--format',
                        'kicadxml', '-o', str(exported), str(SHEET)],
                       check=True, capture_output=True, text=True)
        components = ET.parse(exported).getroot().findall('./components/comp')
    rows = {}
    for component in components:
        source_id = next((field.text for field in component.findall('./fields/field')
                          if field.get('name') == 'SourceId'), None)
        if source_id in SPECS:
            if source_id in rows:
                raise ValueError('duplicate vertical output source '+source_id)
            rows[source_id] = (component.get('ref'), component.findtext('value'))
    if set(rows) != set(SPECS):
        raise ValueError('V27/V28 missing from KiCad output sheet')
    for source_id, (model, _, _, _) in SPECS.items():
        if rows[source_id][1] != model:
            raise ValueError(source_id+' selects a different output model')
    return rows


def numeric(token):
    suffixes = {'p': 1e-12, 'n': 1e-9, 'u': 1e-6, 'm': 1e-3}
    scale = suffixes.get(token[-1], 1)
    return float(token[:-1] if scale != 1 else token)*scale


def bias_at(target_a, vce_v, model, pnp, path):
    low, high = 1e-9, .2
    for _ in range(27):
        base_a = (low+high)/2
        stimulus = (f'VCE c 0 {-vce_v if pnp else vce_v}\n'
                    + (f'IBASE b 0 {base_a}' if pnp else f'IBASE 0 b {base_a}'))
        point = bench.op(stimulus, ('i(vce)', 'v(b)'), model, path)
        current = point['i(vce)'] if pnp else -point['i(vce)']
        if current > target_a:
            high = base_a
        else:
            low = base_a
    base_a = (low+high)/2
    stimulus = (f'VCE c 0 {-vce_v if pnp else vce_v}\n'
                + (f'IBASE b 0 {base_a}' if pnp else f'IBASE 0 b {base_a}'))
    point = bench.op(stimulus, ('i(vce)', 'v(b)'), model, path)
    current = point['i(vce)'] if pnp else -point['i(vce)']
    return dict(collector_current_a=current, base_current_a=base_a,
                collector_emitter_voltage_v=vce_v, hFE=current/base_a)


def ac_ft_proxy(base_a, model, pnp, path):
    source = (f'IBASE b 0 DC {base_a} AC 1' if pnp
              else f'IBASE 0 b DC {base_a} AC 1')
    output = bench.simulate(f'VCE c 0 {-5 if pnp else 5}\n'+source,
                            'ac lin 1 10e6 10e6', ('mag(i(vce))',), model, path)
    match = bench.AC_GAIN.search(output)
    if not match:
        raise RuntimeError('missing BD139/BD140 AC current-gain proxy')
    return 10e6*float(match.group(1))


def run():
    register = json.loads(REGISTER.read_text())
    profile = json.loads(PROFILE.read_text())['parameters']
    entries = {row['id']: row for row in register['devices'] if row['id'] in SPECS}
    if set(entries) != set(SPECS):
        raise ValueError('V27/V28 device register incomplete')
    active = active_models()
    rows = []
    with tempfile.TemporaryDirectory() as directory:
        resolved = Path(directory)/'output-models.cir'
        resolved.write_text(MODELS.read_text()
                            .replace('{output_bf}', str(profile['output_bf']['nominal']))
                            .replace('{output_n_tf}', str(profile['output_n_tf']['nominal']))
                            .replace('{output_p_tf}', str(profile['output_p_tf']['nominal'])))
        for source_id, (model, pnp, tf_key, typical_ft) in SPECS.items():
            entry = entries[source_id]
            if entry['model'] != model:
                raise ValueError(source_id+' register model mismatch')
            match = re.search(r'^\.model '+model+r' (?:NPN|PNP)\(([^)]*)\)',
                              MODELS.read_text(), re.M)
            if not match:
                raise ValueError('missing active '+model+' model')
            tokens = dict(re.findall(r'([A-Z]+)=([^\s]+)', match.group(1)))
            if set(tokens) != (set(entry['parameters'])-{'TF_s'})|{'TF'}:
                raise ValueError(model+' register does not cover live model keys')
            if tokens['BF'] != '{output_bf}' or tokens['TF'] != '{'+tf_key+'}':
                raise ValueError(model+' profile binding changed')
            for key, token in tokens.items():
                if key not in ('BF', 'TF') and abs(numeric(token)-entry['parameters'][key]['nominal']) > 1e-9*max(abs(numeric(token)), 1e-15):
                    raise ValueError(model+' register nominal differs from '+key)
            for key, profile_key in [('BF', 'output_bf'), ('TF_s', tf_key)]:
                parameter = entry['parameters'][key]
                selected = profile[profile_key]
                if (parameter['nominal'], parameter['bounds']) != (
                        selected['nominal'], [selected['minimum'], selected['maximum']]):
                    raise ValueError(model+' profile bounds differ from register')
            gain_150 = bias_at(.15, 2, model, pnp, resolved)
            gain_500 = bias_at(.5, 2, model, pnp, resolved)
            ac_bias = bias_at(.05, 5, model, pnp, resolved)
            ft = ac_ft_proxy(ac_bias['base_current_a'], model, pnp, resolved)
            saturation = bench.op(('ICLOAD c 0 .5\nIBASE b 0 .05' if pnp
                                   else 'ICLOAD 0 c .5\nIBASE 0 b .05'),
                                  ('v(c)', 'v(b)'), model, resolved)
            sat_v = abs(saturation['v(c)'])
            checks = dict(gain_150ma=40 <= gain_150['hFE'] <= 250,
                          gain_500ma=gain_500['hFE'] >= 25,
                          saturation_500ma=sat_v <= .5,
                          bias_reached=all(abs(point['collector_current_a']-target) < .01*target
                                           for point, target in ((gain_150, .15),
                                                                 (gain_500, .5),
                                                                 (ac_bias, .05))))
            rows.append(dict(source_id=source_id, assembly_reference=active[source_id][0],
                             active_model=model, explicit_model_parameters=tokens,
                             gain_at_150ma=gain_150, gain_at_500ma=gain_500,
                             saturation_500ma_v=sat_v, ac_bias_at_50ma=ac_bias,
                             transition_frequency_proxy_hz=ft,
                             philips_typical_transition_frequency_hz=typical_ft,
                             checks=checks, passed=all(checks.values())))
    return dict(format='dac-monitor-vertical-output-bjt-class-check-v1',
                qualification='BD139/BD140 class DC checks and typical fT comparison; '
                              'factory polarity/identity, joint bounds and connected stress remain open',
                sources={'st': register['sources']['st_bd139_bd140'],
                         'philips': register['sources']['philips_bd139_bd140']},
                model_file_sha256=sha(MODELS), profile_sha256=sha(PROFILE),
                register_sha256=sha(REGISTER), sheet_sha256=sha(SHEET),
                devices=rows, passed=all(row['passed'] for row in rows))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = run()
    args.output.write_text(json.dumps(report, indent=2)+'\n')
    for row in report['devices']:
        print(f"{row['source_id']}: hFE150={row['gain_at_150ma']['hFE']:.1f}, "
              f"hFE500={row['gain_at_500ma']['hFE']:.1f}, "
              f"VCEsat={row['saturation_500ma_v']:.3f} V, "
              f"fT proxy={row['transition_frequency_proxy_hz']/1e6:.1f} MHz")
    if not report['passed']:
        raise SystemExit(2)
