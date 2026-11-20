"""Check the live vertical KFY18 PNP proxy against the 1987 Tesla catalog.

This is an isolated model-response check, not a connected-stage stress result.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import tempfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent
REGISTER = ROOT/'reference/k7222-11/device-model-register.json'
MODELS = ROOT/'circuits/k7222-11-vertical-integrator-models.cir'
MODEL = 'VERTICAL_PNP_BOUND'
FAMILY = 'KFY18-vertical-pnp'
SHEETS = {
    '012-6931:V13': ROOT/'circuits/k7222-11-vertical-integrator.kicad_sch',
    '012-6931:V26': ROOT/'circuits/k7222-11-vertical-output.kicad_sch',
}
VALUE = re.compile(r'(i\(vce\)|v\(c\)|v\(b\)|mag\(i\(vce\)\))\s*=\s*([-+\d.eE]+)')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def active_models():
    found = {}
    with tempfile.TemporaryDirectory() as directory:
        for source_id, sheet in SHEETS.items():
            xml = Path(directory)/(source_id.replace(':', '-')+'.xml')
            subprocess.run(['kicad-cli', 'sch', 'export', 'netlist', '--format',
                            'kicadxml', '-o', str(xml), str(sheet)],
                           check=True, capture_output=True, text=True)
            rows = []
            for component in ET.parse(xml).getroot().findall('./components/comp'):
                identity = next((field.text for field in component.findall('./fields/field')
                                 if field.get('name') == 'SourceId'), None)
                if identity == source_id:
                    rows.append((component.get('ref'), component.findtext('value')))
            if len(rows) != 1 or rows[0][1] != MODEL:
                raise ValueError(source_id+' does not select the checked KFY18 model')
            found[source_id] = rows[0][0]
    return found


def model_parameters(family):
    match = re.search(r'^\.model '+MODEL+r' PNP\(([^)]*)\)', MODELS.read_text(), re.M)
    if not match:
        raise ValueError('live KFY18 PNP model is absent')
    tokens = dict(re.findall(r'([A-Z]+)=([^\s]+)', match.group(1)))
    if set(tokens) != set(family['parameters']):
        raise ValueError('KFY18 register does not cover every explicit parameter')
    profiles = [family['profile'], family['other_live_profile']]
    for key, parameter in family['parameters'].items():
        token = tokens[key]
        if 'profile_key' in parameter:
            if token != '{'+parameter['profile_key']+'}':
                raise ValueError('KFY18 BF is not connected to the profile')
            for profile_name in profiles:
                value = json.loads((ROOT/profile_name).read_text())['parameters'][parameter['profile_key']]
                if (value['nominal'], value['minimum'], value['maximum']) != (
                        parameter['nominal'], *parameter['bounds']):
                    raise ValueError('KFY18 live profile differs from register: '+profile_name)
        else:
            scales = {'p': 1e-12, 'n': 1e-9, 'u': 1e-6}
            scale = scales.get(token[-1], 1)
            numeric = float(token[:-1] if scale != 1 else token)*scale
            if not math.isclose(numeric, parameter['nominal'], rel_tol=1e-10):
                raise ValueError('KFY18 model differs from register: '+key)
    return tokens, match.group(0).replace('{retrace_bf}', str(family['parameters']['BF']['nominal']))


def simulate(model_line, circuit, analysis, probes):
    deck = ('KFY18 catalog comparison\n.temp 25\n'+model_line+'\n'+circuit
            +'\n.control\nset noaskquit\n'+analysis+'\n'+probes
            +'\nquit\n.endc\n.end\n')
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory)/'check.cir'
        path.write_text(deck)
        result = subprocess.run(['ngspice', '-n', '-b', str(path)],
                                capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError('ngspice KFY18 check failed: '+result.stdout[-500:]+result.stderr[-500:])
    return result.stdout


def op(model_line, stimulus, probes):
    output = simulate(model_line, 'Q1 c b 0 '+MODEL+'\n'+stimulus,
                      'op', 'print '+' '.join(probes))
    values = {key: float(value) for key, value in VALUE.findall(output)}
    if set(values) != set(probes):
        raise RuntimeError('ngspice omitted KFY18 operating point: '+output[-500:])
    return values


def gain_at(model_line, target_a, vce_v):
    low, high = 1e-10, 1e-2
    for _ in range(30):
        base = (low+high)/2
        point = op(model_line, f'VCE c 0 -{vce_v}\nIBASE b 0 {base:.12g}',
                   ('i(vce)', 'v(b)'))
        if point['i(vce)'] > target_a:
            high = base
        else:
            low = base
    base = (low+high)/2
    point = op(model_line, f'VCE c 0 -{vce_v}\nIBASE b 0 {base:.12g}',
               ('i(vce)', 'v(b)'))
    return dict(collector_current_a=point['i(vce)'], base_current_a=base,
                collector_emitter_voltage_v=-vce_v,
                base_emitter_voltage_v=point['v(b)'], hFE=point['i(vce)']/base)


def ac_gain_at(model_line, base_a):
    output = simulate(model_line,
                      f'Q1 c b 0 {MODEL}\nVCE c 0 -10\nIBASE b 0 DC {base_a:.12g} AC 1',
                      'ac lin 1 30Meg 30Meg', 'print mag(i(vce))')
    values = dict(VALUE.findall(output))
    if 'mag(i(vce))' not in values:
        raise RuntimeError('ngspice omitted KFY18 AC gain: '+output[-500:])
    return float(values['mag(i(vce))'])


def capacitances(model_line):
    output = simulate(model_line,
                      f'Q1 c b e {MODEL}\nVBE e b -0.5\nVCB b c 10\nREXT e 0 1G',
                      'op', 'show q1')
    values = dict(re.findall(r'^\s*(cpi|cmu|vbe|vbc)\s+([-+\d.eE]+)', output, re.M))
    if set(values) != {'cpi', 'cmu', 'vbe', 'vbc'}:
        raise RuntimeError('ngspice omitted KFY18 reverse-bias capacitances')
    return {key: float(value) for key, value in values.items()}


def run():
    register = json.loads(REGISTER.read_text())
    matches = [row for row in register['families'] if row['id'] == FAMILY]
    if len(matches) != 1 or set(matches[0]['member_ids']) != set(SHEETS):
        raise ValueError('KFY18 family coverage differs from live instances')
    family = matches[0]
    tokens, model_line = model_parameters(family)
    active = active_models()
    at_1ma = gain_at(model_line, .001, 5)
    at_10ma = gain_at(model_line, .01, 10)
    at_50ma = gain_at(model_line, .05, 10)
    ac_gain = ac_gain_at(model_line, at_50ma['base_current_a'])
    sat = op(model_line, 'ICLOAD c 0 .15\nIBASE b 0 .015', ('v(c)', 'v(b)'))
    caps = capacitances(model_line)
    targets = family['comparison_targets']
    checks = dict(
        gain_1ma=targets['hFE_1ma']['range'][0] <= at_1ma['hFE'] <= targets['hFE_1ma']['range'][1],
        gain_10ma=targets['hFE_10ma']['range'][0] <= at_10ma['hFE'] <= targets['hFE_10ma']['range'][1],
        saturation=0 <= -sat['v(c)'] <= targets['VCEsat_v']['maximum'],
        transition_frequency_proxy=30e6*ac_gain >= targets['fT_hz']['minimum'],
        collector_base_capacitance=0 < caps['cmu'] <= targets['Ccbo_f']['maximum'],
        emitter_base_capacitance=0 < caps['cpi'] <= targets['Cebo_f']['maximum'],
        capacitance_biases=math.isclose(caps['vbe'], -.5) and math.isclose(caps['vbc'], -10),
    )
    return dict(format='dac-monitor-kfy18-model-check-v1',
                qualification='isolated original-type catalog response; connected stress and joint bounds remain open',
                source=register['sources']['tesla_kfy18_1987'],
                register_sha256=sha(REGISTER), model_file_sha256=sha(MODELS),
                sheet_sha256={key: sha(path) for key, path in SHEETS.items()},
                assembly_references=active, explicit_model_parameters=tokens,
                catalog_targets=targets, gain_at_1ma=at_1ma, gain_at_10ma=at_10ma,
                ac_bias_at_50ma=at_50ma, ac_current_gain_at_30mhz=ac_gain,
                transition_frequency_proxy_hz=30e6*ac_gain,
                saturation=dict(collector_current_a=.15, base_current_a=.015,
                                collector_emitter_voltage_v=sat['v(c)'],
                                base_emitter_voltage_v=sat['v(b)']),
                reverse_bias_capacitances=caps, checks=checks, passed=all(checks.values()))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = run()
    args.output.write_text(json.dumps(report, indent=2)+'\n')
    print(f"KFY18 class check: {sum(report['checks'].values())}/{len(report['checks'])} passed; "
          f"fT proxy {report['transition_frequency_proxy_hz']/1e6:.1f} MHz")
    return 0 if report['passed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
