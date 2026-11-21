"""Exercise declared MAA723 internal-model bounds against isolated 723 targets.

Each internal model moves as a correlated low/high group. This deliberately
does not claim exhaustive coverage of the 48-dimensional parameter box.
"""
import argparse
import copy
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
    lower_dissipation = op(parameters, supply=9.5, load_ohm=6.5/.15,
                           divider_top_ohm=650, divider_bottom_ohm=6500, **common)
    droop = loads['1ma']['output_v']-loads['50ma']['output_v']
    checks = dict(reference=targets['reference_v']['range'][0]
                  <= standby['reference_v'] <= targets['reference_v']['range'][1],
                  standby=0 < standby['supply_current_a']
                  <= targets['standby_current_a']['maximum'],
                  load_regulation=abs(droop) <= targets['load_regulation_v']['maximum'])
    return dict(temperature_c=temperature, reference_v=standby['reference_v'],
                standby_current_a=standby['supply_current_a'],
                load_regulation_v=droop,
                engineering_150ma_probe={
                    'load_resistance_ohm': 100/3,
                    'output_v': loads['150ma']['output_v'],
                    'actual_load_current_a': loads['150ma']['load_current_a'],
                    'pass_power_proxy_w': loads['150ma']['pass_power_proxy_w'],
                    'meets_4p9v_proxy': loads['150ma']['output_v']
                                          >= targets['output_150ma_v']['minimum']},
                lower_dissipation_150ma_probe={
                    'input_v': 9.5, 'setpoint_v': 6.5,
                    'load_resistance_ohm': 6.5/.15,
                    'output_v': lower_dissipation['output_v'],
                    'actual_load_current_a': lower_dissipation['load_current_a'],
                    'chip_power_proxy_w': lower_dissipation['chip_power_proxy_w'],
                    'reaches_145ma_engineering_proxy': lower_dissipation['load_current_a'] >= .145},
                comparisons_to_25c_targets=checks)


def pass_corner_attribution(model_file, source, internal, parameters):
    """Separate the pass BJT's BF/IKF interaction from other low corners."""
    nominal = {name: 'nominal' for name in NAMES}
    low_pass = nominal | {'M723_PASS': 'low'}

    def probe(selection, register, settings=parameters):
        model_file.write_text(rewrite(source, selection, register))
        return maa723_model_check.op(
            settings, supply=9.5, load_ohm=6.5/.15,
            divider_top_ohm=650, divider_bottom_ohm=6500,
            model_file=model_file)['load_current_a']

    one_low = {}
    for key in ('BF', 'IKF'):
        varied = copy.deepcopy(internal)
        varied['M723_PASS'][key]['value'] = varied['M723_PASS'][key]['bounds'][0]
        one_low[key] = probe(nominal, varied)

    restored = {}
    for keys in ((), ('BF',), ('IKF',), ('BF', 'IKF')):
        varied = copy.deepcopy(internal)
        for key in keys:
            varied['M723_PASS'][key]['bounds'][0] = varied['M723_PASS'][key]['value']
        restored['+'.join(keys) or 'none'] = probe(low_pass, varied)

    low_bf_ikf = copy.deepcopy(internal)
    for key in ('BF', 'IKF'):
        low_bf_ikf['M723_PASS'][key]['value'] = low_bf_ikf['M723_PASS'][key]['bounds'][0]
    drive = {}
    for label, current in [('low', parameters['m723_drive_limit']['bounds'][0]),
                           ('nominal', parameters['m723_drive_limit']['nominal']),
                           ('high', parameters['m723_drive_limit']['bounds'][1])]:
        settings = copy.deepcopy(parameters)
        settings['m723_drive_limit']['nominal'] = current
        drive[label] = dict(base_drive_ceiling_a=current,
                            load_current_a=probe(nominal, low_bf_ikf, settings))
    if (not .061 < restored['none'] < .063
            or not .149 < restored['BF+IKF'] < .150
            or drive['high']['load_current_a'] >= .145):
        raise ValueError('MAA723 pass-corner attribution changed')
    return dict(probe='9.5 V input, 6.5 V intended output, 43.333 ohm load, 25 C',
                pass_bjt_bounds=dict(BF=internal['M723_PASS']['BF']['bounds'],
                                     IKF=internal['M723_PASS']['IKF']['bounds']),
                one_parameter_low_load_current_a=one_low,
                restore_nominal_from_all_low_pass_load_current_a=restored,
                low_bf_ikf_drive_ceiling_sweep=drive,
                interpretation='The arbitrary pass-transistor BF and IKF lower bounds jointly cause the low-pass DC failure. Restoring both nominal values recovers about 150 mA even with every other pass model parameter low. The behavioral base-drive upper bound does not rescue the two-parameter low corner; none of these internal values is a manufacturer MAA723 limit.')


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
                             class_checks_at_25c_pass=all(results[1]['comparisons_to_25c_targets'].values()),
                             engineering_4p9v_probe_at_25c_pass=results[1]['engineering_150ma_probe']['meets_4p9v_proxy'],
                             lower_dissipation_145ma_probe_at_25c_pass=results[1]['lower_dissipation_150ma_probe']['reaches_145ma_engineering_proxy']))
        attribution = pass_corner_attribution(model_file, source, internal, entry['parameters'])
    return dict(format='dac-monitor-maa723-internal-corner-screen-v2',
                qualification='nine correlated internal-model cases at three temperatures; 25 C data-sheet comparisons separated from a thermally unqualified 150 mA resistor probe',
                model_sha256=sha(MODEL), class_register_sha256=sha(REGISTER),
                device_register_sha256=sha(maa723_model_check.REGISTER),
                script_sha256=sha(Path(__file__)),
                cases=len(rows), temperatures_c=list(TEMPERATURES_C),
                target_source=register['sources']['ti_lm723'],
                comparison_targets=targets,
                ideal_5v_150ma_pass_power_w_at_12v=1.05,
                lm723_25c_package_power_ratings_w={'metal_can': .8, 'cdip': .9, 'pdip': .66},
                rows=rows,
                class_check_failures_at_25c=sum(not row['class_checks_at_25c_pass'] for row in rows),
                engineering_probe_misses_at_25c=sum(not row['engineering_4p9v_probe_at_25c_pass'] for row in rows),
                lower_dissipation_probe_misses_at_25c=sum(not row['lower_dissipation_145ma_probe_at_25c_pass'] for row in rows),
                pass_corner_attribution=attribution,
                limitations=['All low/high shifts within each internal model are correlated; arbitrary mixed corners are not covered.',
                             'The 25 C comparison targets are reused only as sensitivity references at 0 and 70 C, not claimed data-sheet limits at those temperatures.',
                             'The 33.33 ohm resistor draws 150 mA only near 5 V. At the low-pass corner, its actual current is about 67 mA. A regulated 5 V/150 mA point at 12 V would dissipate about 1.05 W in the pass path, above every listed LM723 package rating at 25 C, so the 4.9 V probe is not a family qualification gate.',
                             'The 9.5 V/6.5 V/150 mA intended point lies within the uA723 recommended voltage, differential and current envelope and is below the LM723 PDIP 25 C power comparator at nominal; the sheets do not guarantee 145 mA or a particular output voltage in this setup, so its threshold remains an engineering proxy.',
                             'The isolated DC setup does not exercise current-limit switching, transient stability, connected device stress or the 30 pF pole.'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    report = run()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2)+'\n')
    print(f"{report['class_check_failures_at_25c']} class-check failures; "
          f"{report['engineering_probe_misses_at_25c']} miss the 4.9 V probe, "
          f"{report['lower_dissipation_probe_misses_at_25c']} miss the lower-dissipation 145 mA probe")
