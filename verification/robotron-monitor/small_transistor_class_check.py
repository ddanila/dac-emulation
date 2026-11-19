"""Check live 1SA20C/1SC60A proxies against a BC546B-class comparator."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import tempfile

import horizontal_driver_transistor_check as bench
import steady_supply


ROOT = Path(__file__).resolve().parent
REGISTER = ROOT/'reference/k7222-11/device-model-register.json'
MODELS = ROOT/'circuits/k7222-11-small-transistor-models.cir'
SOURCE = 'https://www.onsemi.com/download/data-sheet/pdf/bc546-d.pdf'
FAMILIES = {
    '1SA20C': ('SA20C_CLASS_N', {'012-6921:V6', '012-6921:V19', '012-6921:V20',
                                  '012-6931:V5', '012-6931:V11'}),
    '1SC60A': ('SC60A_CLASS_N', {'012-6921:V1', '012-6921:V5'}),
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def model_parameters(model):
    match = re.search(r'^\.model ' + re.escape(model) + r' NPN\(([^)]*)\)',
                      MODELS.read_text(), re.M)
    if not match:
        raise ValueError('missing live class model '+model)
    scales = {'p': 1e-12, 'n': 1e-9, 'u': 1e-6}
    values = {}
    for key, token in re.findall(r'([A-Z]+)=([^\s]+)', match.group(1)):
        scale = scales.get(token[-1], 1)
        values[key] = float(token[:-1] if scale != 1 else token)*scale
    return values


def run():
    register = json.loads(REGISTER.read_text())
    if register['sources']['onsemi_bc546b']['url'] != SOURCE:
        raise ValueError('BC546B source changed without review')
    with tempfile.TemporaryDirectory() as directory:
        assembly = steady_supply.assemble(Path(directory)/'assembly')
    if sum('.model SA20C_CLASS_N NPN' in text for text in assembly['models']) != 1:
        raise ValueError('small-transistor model not loaded exactly once')
    active = {row['source_id']: row for row in assembly['components']}
    rows = []
    for printed_type, (model, ids) in FAMILIES.items():
        matches = [row for row in register['families']
                   if row.get('printed_type') == printed_type and row.get('model') == model]
        if len(matches) != 1 or set(matches[0]['member_ids']) != ids:
            raise ValueError(printed_type+' family register membership differs')
        entry = matches[0]
        if any(active[source_id]['value'] != model for source_id in ids):
            raise ValueError(printed_type+' assembled model differs')
        parameters = model_parameters(model)
        if set(parameters) != set(entry['parameters']):
            raise ValueError(printed_type+' parameter coverage differs from model')
        for key, value in parameters.items():
            spec = entry['parameters'][key]
            if not math.isclose(value, spec['nominal'], rel_tol=1e-10):
                raise ValueError(printed_type+' nominal parameter mismatch: '+key)
            if not spec['bounds'][0] <= value <= spec['bounds'][1]:
                raise ValueError(printed_type+' parameter outside recorded bounds: '+key)
        gain = bench.gain_at(.002, 5, model, MODELS)
        ac_bias = bench.gain_at(.01, 5, model, MODELS)
        ft_proxy = 100e6*bench.ac_gain_at(ac_bias['base_current_a'], 5, 100e6,
                                          model, MODELS)
        saturation = bench.op('ICLOAD 0 c .01\nIBASE 0 b .0005',
                              ('v(c)', 'v(b)'), model, MODELS)
        targets = entry['comparison_targets']
        checks = {
            'two_ma_gain': targets['hFE_2ma']['range'][0] <= gain['hFE'] <= targets['hFE_2ma']['range'][1],
            'ten_ma_saturation': 0 <= saturation['v(c)'] <= targets['VCEsat_v']['maximum'],
            'transition_frequency_proxy': ft_proxy >= targets['fT_hz']['minimum'],
            'gain_bias_reached': abs(gain['collector_current_a']-.002) < .00002,
            'ac_bias_reached': abs(ac_bias['collector_current_a']-.01) < .0001,
        }
        rows.append(dict(printed_type=printed_type, model=model,
                         member_ids=sorted(ids), parameters=parameters,
                         hFE_at_2ma_5v=gain['hFE'],
                         VCEsat_at_10ma_0p5ma_v=saturation['v(c)'],
                         transition_frequency_proxy_hz=ft_proxy,
                         comparison_targets=targets, checks=checks,
                         passed=all(checks.values())))
    return dict(format='dac-monitor-small-transistor-class-check-v1',
                qualification='BC546B-class isolated DC/AC comparison for unidentified printed types; original identity, connected stress and joint bounds remain open',
                source=SOURCE, model_sha256=sha(MODELS), register_sha256=sha(REGISTER),
                rows=rows, passed=all(row['passed'] for row in rows))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = run()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2)+'\n')
    for row in report['rows']:
        print(f"{row['printed_type']}: hFE {row['hFE_at_2ma_5v']:.1f}, "
              f"VCEsat {row['VCEsat_at_10ma_0p5ma_v']:.3f} V, "
              f"fT proxy {row['transition_frequency_proxy_hz']/1e6:.1f} MHz")
    return 0 if report['passed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
