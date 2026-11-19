"""Sweep provisional vertical-diode bounds through the connected vertical bench.

This is a one-parameter-at-a-time stage sensitivity check. It does not identify
the original 1AE15 or qualify the connected native-frame monitor.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile

import reference

ROOT = Path(__file__).resolve().parent
PROFILE = ROOT/'profiles/k7222-11-vertical-output.json'
REGISTER = ROOT/'reference/k7222-11/device-model-register.json'
MODEL = ROOT/'circuits/k7222-11-vertical-integrator-models.cir'
LINE = re.compile(r'(?m)^\.model VERTICAL_DIODE D\(([^\n)]*)\)$')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def metrics(rows, probes, field_start):
    indexes = {probe['name']: i+1 for i, probe in enumerate(probes)}
    final = [row for row in rows if row[0] >= field_start]
    if len(final) < 100:
        raise ValueError('final vertical field is incomplete')
    result = {}
    for name in ('yoke', 'ramp', 'pulse'):
        values = [row[indexes[name]] for row in final]
        result[name+'_peak_to_peak'] = max(values)-min(values)
    result['yoke_mean'] = sum(row[indexes['yoke']] for row in final)/len(final)
    return result


def deck_with_bound(deck, name, value):
    match = LINE.search(deck)
    if not match or len(LINE.findall(deck)) != 1:
        raise ValueError('expected exactly one VERTICAL_DIODE model')
    parameters = match.group(1)
    updated, count = re.subn(r'(?<!\w)'+re.escape(name)+r'=[^\s)]+',
                             name+'='+format(value, '.15g'), parameters)
    if count != 1:
        raise ValueError('diode parameter missing or repeated: '+name)
    return deck[:match.start(1)] + updated + deck[match.end(1):]


def run():
    register = json.loads(REGISTER.read_text())
    family = next(f for f in register['families'] if f['id']=='1AE15-vertical-signal-diode')
    profile = json.loads(PROFILE.read_text())
    period = profile['parameters']['sync_period']['nominal']
    stop, step = .16, 10e-6
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        baseline_report = reference.run(PROFILE, root/'baseline', stop=stop, step=step)
        actual_members = {part['source_id'] for part in baseline_report['components']
                          if part['value']=='VERTICAL_DIODE'}
        if actual_members != set(family['member_ids']):
            raise ValueError('vertical stage diodes differ from registered family')
        deck = (root/'baseline/run.cir').read_text()
        base_rows = reference.read_samples(root/'baseline/samples.txt',
                                           baseline_report['probes'], 0, stop, step)
        baseline = metrics(base_rows, baseline_report['probes'], stop-period)
        cases = []
        for name, parameter in family['parameters'].items():
            for bound, value in zip(('minimum','maximum'), parameter['bounds']):
                path = root/(name+'-'+bound)
                path.mkdir()
                (path/'run.cir').write_text(deck_with_bound(deck, name, value))
                solve = subprocess.run(['ngspice','-n','-b','run.cir'], cwd=path,
                                       capture_output=True, text=True)
                log = solve.stdout+solve.stderr
                if solve.returncode or re.search(r'(?im)^\s*(?:error|fatal|warning)|timestep too small|singular matrix|simulation interrupted', log):
                    raise RuntimeError('vertical diode bound solve failed: '
                                       +name+' '+bound+' '+log[-500:])
                rows = reference.read_samples(path/'samples.txt',
                                              baseline_report['probes'], 0, stop, step)
                observed = metrics(rows, baseline_report['probes'], stop-period)
                changes = {key: observed[key]-baseline[key] for key in baseline}
                cases.append(dict(parameter=name, bound=bound, value=value,
                                  metrics=observed, delta=changes))
    maximum = {key: max(abs(case['delta'][key]) for case in cases) for key in baseline}
    relative = {key: maximum[key]/abs(baseline[key]) if baseline[key] else None
                for key in baseline}
    return dict(format='dac-monitor-1ae15-vertical-stage-sensitivity-v1',
                qualification='one-at-a-time provisional bounds on 20.8 ms stage bench; original part and native connected frame unverified',
                model_sha256=digest(MODEL), profile_sha256=digest(PROFILE),
                register_sha256=digest(REGISTER),
                stage_source_hashes=baseline_report['hashes'],
                solver_version=baseline_report['solver']['version'],
                family_id=family['id'], member_ids=family['member_ids'],
                stop_s=stop, sample_step_s=step, final_field_start_s=stop-period,
                baseline=baseline, cases=cases,
                maximum_absolute_delta=maximum,
                maximum_fractional_delta=relative)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    report = run()
    args.output.write_text(json.dumps(report, indent=2)+'\n')
    print('swept', len(report['cases']), 'diode-bound cases; max yoke span change',
          f"{100*report['maximum_fractional_delta']['yoke_peak_to_peak']:.2f}%")


if __name__ == '__main__':
    main()
