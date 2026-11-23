"""Screen SSY20A model timing at the cited 500 mA/80 ohm switching condition."""
import hashlib
import itertools
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parent
PROFILE = ROOT / 'profiles/k7222-11-neck.json'
MODELS = ROOT / 'circuits/k7222-11-neck-models.cir'
OUTPUT = ROOT / 'reference/k7222-11/ssy20-switching-corner-screen.json'
SOURCE_READ = ROOT / 'reference/k7222-11/ssy20-datasheet-direct-read.json'
DYNAMIC = ('q_bf', 'q_ikf', 'q_rb', 'q_cje', 'q_cjc', 'q_tf', 'q_tr')
ACTIVE_MAX = {'q_tf': 3.2e-9, 'q_tr': 40e-9}
HISTORICAL_MAX = {'q_tf': 20e-9, 'q_tr': 100e-9}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def crossing(rows, start, threshold, falling):
    previous = None
    for time, voltage in rows:
        if time < start:
            previous = (time, voltage)
            continue
        reached = voltage <= threshold if falling else voltage >= threshold
        if reached:
            if previous is None or previous[1] == voltage:
                return time
            t0, v0 = previous
            return t0 + (time - t0) * (threshold - v0) / (voltage - v0)
        previous = (time, voltage)
    return None


def solve(parameters, model, directory):
    deck = ('SSY20A conditional switching fixture\n.temp 25\n'
            + ''.join(f'.param {key}={value}\n' for key, value in parameters.items())
            + model + '\nVCC vcc 0 40\nRLOAD vcc c 80\n'
            + 'IBASE 0 b PWL(0 0 99n 0 100n 0.05 299n 0.05 '
              '300n -0.025 500n -0.025 501n 0)\n'
            + 'Q1 c b 0 SSY20A_BOUND\n.control\ntran 0.2n 520n\n'
              'wrdata trace.txt v(c)\nquit\n.endc\n.end\n')
    path = directory / 'switch.cir'
    path.write_text(deck)
    result = subprocess.run(['ngspice', '-b', str(path)], cwd=directory,
                            capture_output=True, text=True)
    if result.returncode or 'Error:' in result.stdout + result.stderr:
        raise ValueError('ngspice SSY20 switching failure: ' + (result.stdout + result.stderr)[-500:])
    rows = [tuple(map(float, line.split()[:2]))
            for line in (directory / 'trace.txt').read_text().splitlines() if line.strip()]
    if len(rows) < 1000 or rows[-1][0] < 520e-9 - 1e-12:
        raise ValueError('incomplete SSY20 switching trace')
    on = crossing(rows, 100e-9, 4.0, True)
    off = crossing(rows, 300e-9, 36.0, False)
    on_ns = None if on is None else (on - 100e-9) * 1e9
    off_ns = None if off is None else (off - 300e-9) * 1e9
    return dict(on_ns=on_ns, off_ns=off_ns,
                source_limits_met=on_ns is not None and off_ns is not None
                                  and 0 <= on_ns <= 50 and 0 <= off_ns <= 100)


def run():
    ngspice = shutil.which('ngspice')
    if ngspice is None:
        raise ValueError('ngspice executable not found')
    profile = json.loads(PROFILE.read_text())
    source = json.loads(SOURCE_READ.read_text())
    if (source['switching_tests']['ton_max_ns'] != 50 or
            source['switching_tests']['toff_max_ns'] != 100 or
            source['limits']['ic_a'] != .6):
        raise ValueError('direct SSY20 source read changed')
    specs = profile['parameters']
    nominal = {key: spec['nominal'] for key, spec in specs.items()}
    if any(specs[key]['maximum'] != value for key, value in ACTIVE_MAX.items()):
        raise ValueError('SSY20 registered timing bounds changed')
    model = MODELS.read_text()
    with tempfile.TemporaryDirectory() as temporary:
        directory = Path(temporary)
        baseline = solve(nominal, model, directory)
        old_slow = dict(nominal)
        old_slow.update({key: specs[key]['maximum'] for key in DYNAMIC})
        old_slow.update(HISTORICAL_MAX)
        old_corner = solve(old_slow, model, directory)
        cases = []
        for bits in itertools.product((0, 1), repeat=len(DYNAMIC)):
            params = dict(nominal)
            for key, bit in zip(DYNAMIC, bits):
                params[key] = specs[key]['maximum'] if bit else specs[key]['minimum']
            result = solve(params, model, directory)
            cases.append(dict(dynamic_parameters={key: params[key] for key in DYNAMIC},
                              **result))
    passed = (baseline['source_limits_met'] and not old_corner['source_limits_met']
              and len(cases) == 128 and all(row['source_limits_met'] for row in cases))
    return dict(format='dac-monitor-ssy20-switching-corner-screen-v1',
                qualification='active conditional SPICE timing envelope at 40 V/80 ohm and 4/36 V collector thresholds; not a certified datasheet switching test or connected neck stress',
                source_url='https://www.tiffe.de/robotron/Bausteinuebersicht/DDR-Halbleiter.pdf',
                direct_source_read_sha256=sha(SOURCE_READ),
                source_conditions='SSY20: IC=500 mA, IB1=50 mA, reverse IB2=25 mA, RL=80 ohm; ton <=50 ns, toff <=100 ns. 40 V supply and 10/90% collector thresholds are fixture inferences.',
                profile_sha256=sha(PROFILE), models_sha256=sha(MODELS),
                script_sha256=sha(__file__), ngspice_sha256=sha(Path(ngspice).resolve()),
                historical_dynamic_max=HISTORICAL_MAX,
                active_dynamic_max=ACTIVE_MAX,
                nominal=baseline, old_all_maximum=old_corner,
                candidate_corner_count=len(cases),
                candidate_worst_on_ns=max(row['on_ns'] for row in cases),
                candidate_worst_off_ns=max(row['off_ns'] for row in cases),
                candidate_failures=sum(not row['source_limits_met'] for row in cases),
                cases=cases, bounds_promoted=True, a2_qualified=False, passed=passed)


if __name__ == '__main__':
    report = run()
    OUTPUT.write_text(json.dumps(report, indent=2) + '\n')
    print(f"{report['candidate_corner_count']} corners; failures={report['candidate_failures']}; passed={report['passed']}")
    raise SystemExit(0 if report['passed'] else 2)
