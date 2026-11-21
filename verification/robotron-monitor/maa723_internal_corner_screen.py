"""Exercise declared MAA723 internal-model bounds against isolated 723 targets.

Each internal model moves as a correlated low/high group. This deliberately
does not claim exhaustive coverage of the 48-dimensional parameter box.
"""
import argparse
import hashlib
import itertools
import json
from pathlib import Path
import re
import tempfile

import a2_internal_device_audit
import maa723_model_check


ROOT = Path(__file__).resolve().parent
MODEL = ROOT/'circuits/k7222-11-vertical-integrator-models.cir'
REGISTER = ROOT/'reference/k7222-11/class-typical-register.json'
NAMES = ('M723_PASS', 'M723_LIMIT', 'M723_CLAMP')
TEMPERATURES_C = (0, 25, 70)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bounds():
    rows = json.loads(REGISTER.read_text())['entries']
    values = {}
    for name in NAMES:
        prefix = f'012-6931:A2.{name}.'
        group = {row['id'][len(prefix):]: row for row in rows
                 if row['id'].startswith(prefix)}
        live = a2_internal_device_audit.model_values(MODEL, name)
        if set(group) != set(live):
            raise ValueError('internal model and bounds differ: '+name)
        for key, value in live.items():
            row = group[key]
            if (abs(row['value']-value) > max(1e-18, abs(value)*1e-9)
                    or not row['bounds'][0] <= value <= row['bounds'][1]):
                raise ValueError(f'internal nominal/bounds mismatch: {name}.{key}')
        values[name] = group
    return values


def rewrite(source, selections, register):
    for name in NAMES:
        pattern = re.compile(r'^\.model '+name+r'\s+(NPN|D)\((.*?)\)', re.M | re.S)
        def replace(match):
            keys = list(a2_internal_device_audit.model_values(MODEL, name))
            setting = selections[name]
            if setting not in ('nominal', 'low', 'high'):
                raise ValueError('unknown internal model selection: '+setting)
            index = {'low': 0, 'high': 1}.get(setting)
            items = []
            for key in keys:
                row = register[name][key]
                value = row['value'] if index is None else row['bounds'][index]
                items.append(f'{key}={value:.12g}')
            lines = ['.model '+name+' '+match.group(1)+'('+ ' '.join(items[:6])]
            lines += ['+ '+' '.join(items[i:i+6]) for i in range(6, len(items), 6)]
            lines[-1] += ')'
            return '\n'.join(lines)
        source, count = pattern.subn(replace, source)
        if count != 1:
            raise ValueError('expected one model card: '+name)
    return source


def case(model_file, temperature, parameters, targets):
    op = maa723_model_check.op
    common = dict(model_file=model_file, temperature_c=temperature)
    standby = op(parameters, supply=30, **common)
    loads = {name: op(parameters, supply=12, load_ohm=ohm, **common)
             for name, ohm in (('1ma', 5000), ('50ma', 100), ('150ma', 100/3))}
    droop = loads['1ma']['output_v']-loads['50ma']['output_v']
    checks = dict(reference=targets['reference_v']['range'][0]
                  <= standby['reference_v'] <= targets['reference_v']['range'][1],
                  standby=0 < standby['supply_current_a']
                  <= targets['standby_current_a']['maximum'],
                  load_regulation=abs(droop) <= targets['load_regulation_v']['maximum'],
                  output_150ma=loads['150ma']['output_v']
                  >= targets['output_150ma_v']['minimum'])
    return dict(temperature_c=temperature, reference_v=standby['reference_v'],
                standby_current_a=standby['supply_current_a'],
                load_regulation_v=droop,
                output_150ma_v=loads['150ma']['output_v'], checks=checks)


def run():
    register, entry = maa723_model_check.registered_parameters()
    internal = bounds()
    targets = entry['comparison_targets']
    source = MODEL.read_text()
    rows = []
    selections = [dict(zip(NAMES, choices)) for choices in
                  itertools.product(('low', 'high'), repeat=len(NAMES))]
    selections.insert(0, {name: 'nominal' for name in NAMES})
    with tempfile.TemporaryDirectory() as temp:
        model_file = Path(temp)/'model.cir'
        for selection in selections:
            model_file.write_text(rewrite(source, selection, internal))
            results = [case(model_file, temperature, entry['parameters'], targets)
                       for temperature in TEMPERATURES_C]
            rows.append(dict(groups=selection, temperatures=results,
                             all_proxy_checks_pass=all(all(point['checks'].values())
                                                       for point in results)))
    return dict(format='dac-monitor-maa723-internal-corner-screen-v1',
                qualification='nine correlated internal-model cases at three temperatures; isolated family proxy only, not exhaustive joint bounds or an MAA723 identity',
                model_sha256=sha(MODEL), class_register_sha256=sha(REGISTER),
                device_register_sha256=sha(maa723_model_check.REGISTER),
                script_sha256=sha(Path(__file__)),
                cases=len(rows), temperatures_c=list(TEMPERATURES_C),
                target_source=register['sources']['ti_lm723'],
                comparison_targets=targets,
                rows=rows,
                failed_cases=sum(not row['all_proxy_checks_pass'] for row in rows),
                limitations=['All low/high shifts within each internal model are correlated; arbitrary mixed corners are not covered.',
                             'The 25 C comparison targets are reused as engineering proxies at 0 and 70 C, not claimed data-sheet limits at those temperatures.',
                             'The isolated DC setup does not exercise current-limit switching, transient stability, connected device stress or the 30 pF pole.'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    report = run()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2)+'\n')
    print(f"{report['failed_cases']} of {report['cases']} correlated internal-model cases miss an isolated proxy target")
