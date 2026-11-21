"""Screen connected V27/V28 stress against a BD139/BD140 class comparator.

This is an ideal-rail, synthetic-sync vertical stage diagnostic. It does not
identify the installed transistors or establish their junction temperatures.
"""

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import tempfile

import reference


ROOT = Path(__file__).resolve().parent
PROFILE = ROOT / 'profiles/k7222-11-vertical-output.json'
ST_URL = 'https://www.st.com/resource/en/datasheet/bd139.pdf'
STEP_S = 5e-6
STOP_S = .24
SENSE = ('p22', 'n16', 'upper_emitter', 'lower_emitter')
DEVICE = {
    'V27': ('q724', 'p22', 'upper_emitter', False),
    'V28': ('q726', 'n16', 'lower_emitter', True),
}
EXTRA = ' '.join(f'@{q}[{quantity}]' for q in ('q724', 'q726')
                 for quantity in ('ic', 'ib'))


def digest(data):
    return hashlib.sha256(data).hexdigest()


def samples(path):
    with path.open() as stream:
        header = next(stream).split()
        if len(header) != len(set(header)) or header[0] != 'time':
            raise ValueError('invalid or duplicate stress vectors')
        rows = []
        for line in stream:
            row = [float(value) for value in line.split()]
            if (len(row) != len(header) or not all(map(math.isfinite, row))
                    or rows and row[0] <= rows[-1][0]):
                raise ValueError('invalid stress sample')
            rows.append(row)
    if (len(rows) != round(STOP_S / STEP_S) + 1
            or abs(rows[0][0]) > 1e-12 or abs(rows[-1][0] - STOP_S) > 1e-9):
        raise ValueError('incomplete stress recording')
    return {key: i for i, key in enumerate(header)}, rows


def maximum(rows, function):
    value, time = max((function(row), row[0]) for row in rows)
    return {'value': value, 'time_s': time}


def device_metrics(rows, columns, device):
    q, collector, base, pnp = DEVICE[device]
    value = lambda row, vector: row[columns[vector]]
    vce = lambda row: value(row, f'v({collector})') - value(row, 'v(y1)')
    reverse_vbe = (lambda row: value(row, f'v({base})') - value(row, 'v(y1)')) if pnp else (
        lambda row: value(row, 'v(y1)') - value(row, f'v({base})'))
    ic = lambda row: value(row, f'@{q}[ic]')
    ib = lambda row: value(row, f'@{q}[ib]')
    power = lambda row: max(vce(row) * ic(row), 0.)
    metric = {
        'max_abs_vce_v': maximum(rows, lambda row: abs(vce(row))),
        'max_reverse_vbe_v': maximum(rows, reverse_vbe),
        'max_abs_collector_current_a': maximum(rows, lambda row: abs(ic(row))),
        'max_abs_base_current_a': maximum(rows, lambda row: abs(ib(row))),
        'max_positive_collector_power_w': maximum(rows, power),
        'mean_positive_collector_power_w': sum(map(power, rows)) / len(rows),
    }
    metric['class_absolute_max_screen'] = {
        'vce_80v': metric['max_abs_vce_v']['value'] <= 80,
        'reverse_vbe_5v': metric['max_reverse_vbe_v']['value'] <= 5,
        'collector_current_1p5a': metric['max_abs_collector_current_a']['value'] <= 1.5,
        'base_current_0p5a': metric['max_abs_base_current_a']['value'] <= .5,
        'mean_collector_power_1p25w_free_air': metric['mean_positive_collector_power_w'] <= 1.25,
    }
    return metric


def run():
    profile = json.loads(PROFILE.read_text())
    period = profile['parameters']['sync_period']['nominal']
    for node in SENSE:
        profile['probes'].append(dict(name='stress_' + node, expression=f'v({node})',
                                      unit='V', source_id='012-6931:V27' if node in
                                      ('p22', 'upper_emitter') else '012-6931:V28'))
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        profile_path = directory / 'profile.json'
        profile_path.write_text(json.dumps(profile, indent=2) + '\n')
        stage = reference.run(profile_path, directory / 'stage', stop=STOP_S, step=STEP_S)
        deck = (directory / 'stage/run.cir').read_text()
        deck = deck.replace('tran 5e-06', f'save all {EXTRA}\ntran 5e-06', 1)
        deck = deck.replace('linearize v(vertical_supply)',
                            f'linearize {EXTRA} v(vertical_supply)', 1)
        deck = deck.replace('wrdata samples.txt v(vertical_supply)',
                            f'wrdata stress-samples.txt {EXTRA} v(vertical_supply)', 1)
        if deck.count('save all ' + EXTRA) != 1 or deck.count('wrdata stress-samples.txt') != 1:
            raise ValueError('stress vectors not inserted into stage deck')
        (directory / 'stress.cir').write_text(deck)
        with (directory / 'stress.log').open('w') as log:
            subprocess.run(['ngspice', '-n', '-b', 'stress.cir'], cwd=directory,
                           stdout=log, stderr=subprocess.STDOUT, check=True)
        if re.search(r'(?im)^\s*(?:error|fatal|warning)|timestep too small|singular matrix',
                     (directory / 'stress.log').read_text()):
            raise ValueError('stress solver diagnostics rejected')
        columns, rows = samples(directory / 'stress-samples.txt')
        required = {f'@{q}[{quantity}]' for q in ('q724', 'q726')
                    for quantity in ('ic', 'ib')}
        required |= {f'v({node})' for node in (*SENSE, 'y1')}
        if not required <= columns.keys():
            raise ValueError('missing collector or node vectors')
        final = [row for row in rows if row[0] >= STOP_S - 2 * period]
        samples_per_field = round(period / STEP_S)
        first = final[:samples_per_field]
        second = final[samples_per_field:2 * samples_per_field]
        if len(first) != len(second) or not first:
            raise ValueError('incomplete paired fields')
        yoke = columns['i(Lvertical)']
        periodic_error = max(abs(a[yoke] - b[yoke]) for a, b in zip(first, second))
        yoke_span = max(row[yoke] for row in final) - min(row[yoke] for row in final)
        return {
            'format': 'dac-monitor-vertical-output-stress-screen-v1',
            'qualification': 'diagnostic only; synthetic sync, ideal rails, hypothetical yoke, '
                             'nominal models, no case temperature or SOA qualification',
            'source': {'st_bd139_bd140': ST_URL, 'ratings': {
                'vceo_v': 80, 'vebo_v': 5, 'ic_a': 1.5, 'ib_a': .5,
                'ptot_w_at_25c_ambient': 1.25, 'ptot_w_at_25c_case': 12.5}},
            'simulation': {'stop_s': STOP_S, 'sample_step_s': STEP_S,
                           'synthetic_sync_period_s': period,
                           'final_two_field_start_s': STOP_S - 2 * period,
                           'final_two_field_yoke_current_max_difference_a': periodic_error,
                           'final_two_field_yoke_current_span_a': yoke_span,
                           'field_difference_fraction_of_span': periodic_error / yoke_span,
                           'rows': len(rows), 'ngspice_version': subprocess.check_output(
                               ['ngspice', '--version'], text=True).strip()},
            'inputs': {'stage_hashes': stage['hashes'],
                       'stress_deck_sha256': digest(deck.encode()),
                       'script_sha256': digest(Path(__file__).read_bytes())},
            'devices': {device: {'full_run': device_metrics(rows, columns, device),
                                 'final_two_fields': device_metrics(final, columns, device)}
                        for device in DEVICE},
        }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = run()
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    for device, result in report['devices'].items():
        field = result['final_two_fields']
        print(device, 'VCE', round(field['max_abs_vce_v']['value'], 3), 'V, IC',
              round(field['max_abs_collector_current_a']['value'], 3), 'A, mean P',
              round(field['mean_positive_collector_power_w'], 3), 'W')
