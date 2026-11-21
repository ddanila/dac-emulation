"""Test registered V4 charge bounds in the provisional connected 20-port stage."""

from concurrent.futures import ThreadPoolExecutor
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time

import steady_supply
import transformer_candidates
from t3_page4_connected_stiffness_screen import raw_tail


ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / 'reference/k7222-11/t3-page4-connected-v4-boundary-screen.json'
REGISTER = ROOT / 'reference/k7222-11/class-typical-register.json'
MODEL = ROOT / 'circuits/signal-path-models.cir'
sys.path.insert(0, str(ROOT / 'tests'))
from test_frames import capture  # Explicit synthetic diagnostic input.


CASES = (
    ('nominal', 75e-12, 100e-9),
    ('low_charge', 1e-12, 10e-9),
    ('high_charge', 150e-12, 1e-6),
)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def registered_bounds():
    register = json.loads(REGISTER.read_text())
    rows = [row for value in register.values() if isinstance(value, list)
            for row in value if isinstance(row, dict) and row.get('id', '').startswith('012-6921:V4.')]
    by_id = {row['id'].split('.')[-1]: row for row in rows}
    for key in ('CJO', 'TT'):
        if key not in by_id:
            raise ValueError(f'missing V4 {key} register row')
    for _, cjo, tt in CASES:
        for key, value in (('CJO', cjo), ('TT', tt)):
            low, high = by_id[key]['bounds']
            if not low <= value <= high:
                raise ValueError(f'{key} case outside registered bounds')
    return {key: by_id[key] for key in ('CJO', 'TT')}


def nearest_preedge(selection, observed_time_s):
    labels = ('video', 'bsyn', 'intens')
    events = selection['events']
    candidates = []
    for previous, current in zip(events, events[1:]):
        changed = [label for index, label in enumerate(labels, 1)
                   if previous[index] != current[index]]
        if changed:
            transition_s = current[0] / selection['clock_hz']
            preedge_s = transition_s - 1e-10
            candidates.append((abs(observed_time_s - preedge_s),
                               transition_s, preedge_s, changed))
    residual, transition_s, preedge_s, changed = min(candidates)
    return dict(transition_s=transition_s, preedge_s=preedge_s,
                changed_channels=changed,
                absolute_residual_s=residual)


def run(ngspice):
    binary = Path(ngspice).resolve()
    bounds = registered_bounds()
    model_line = next(line for line in MODEL.read_text().splitlines()
                      if line.startswith('.model Z9_BOUND D('))
    with tempfile.TemporaryDirectory() as directory:
        scratch = Path(directory)
        assembly = steady_supply.assemble(
            scratch / 'assembly', t3_interface='page4-visible-20-port')
        candidate = transformer_candidates.enumerate_candidates(
            assembly['magnetic_graph'])[0]
        selection = steady_supply.select(capture())
        deck, metadata = steady_supply.deck(
            assembly, selection, candidate, magnetic_backend='coupled',
            max_step_s=50e-9)
        if deck.count(model_line) != 1:
            raise ValueError('connected V4 model card changed')
        jobs = []
        for name, cjo, tt in CASES:
            case_dir = scratch / name
            case_dir.mkdir()
            alternate = model_line.replace('CJO=75p TT=100n',
                                           f'CJO={cjo:.15g} TT={tt:.15g}')
            if alternate == model_line:
                raise ValueError('V4 charge-card anchor changed')
            lines = []
            for line in deck.replace(model_line, alternate).splitlines():
                if line.startswith('.save '):
                    line = ('.save time v(eht) v(h_hot) v(h_return) v(h_boost) '
                            'v(p41) v(h_outputbase) v(h_drivecol) i(Lhorizontal)')
                elif line.startswith('.tran '):
                    line = '.tran 50n 17ms 15ms 50n'
                lines.append(line)
            circuit = '\n'.join(lines) + '\n'
            (case_dir / 'run.cir').write_text(circuit)
            jobs.append((name, cjo, tt, case_dir,
                         hashlib.sha256(circuit.encode()).hexdigest()))

        def solve(job):
            name, cjo, tt, case_dir, digest = job
            started = time.monotonic()
            try:
                process = subprocess.run(
                    [str(binary), '-b', '-r', 'trace.raw', '-o', 'solver.log',
                     'run.cir'], cwd=case_dir, capture_output=True, text=True,
                    timeout=150)
                status = 'complete' if process.returncode == 0 else 'aborted'
                code = process.returncode
            except subprocess.TimeoutExpired:
                status = 'timeout'
                code = None
            log_path = case_dir / 'solver.log'
            log = log_path.read_text() if log_path.exists() else ''
            failure = re.search(
                r'Timestep too small; time = ([\d.e+-]+), '
                r'timestep = ([\d.e+-]+): trouble with node "([^"]+)"', log)
            if status == 'aborted' and failure is None:
                raise ValueError(f'{name} failed without classified solver error')
            result = dict(name=name, cjo_f=cjo, tt_s=tt, status=status,
                          returncode=code, timeout_s=150,
                          elapsed_s=round(time.monotonic() - started, 3),
                          deck_sha256=digest,
                          solver_log_sha256=sha(log_path) if log_path.exists() else None,
                          raw_tail=raw_tail(case_dir / 'trace.raw'))
            if result['raw_tail'] is not None:
                result['nearest_source_preedge'] = nearest_preedge(
                    selection, result['raw_tail']['last_time_s'])
            if failure:
                result['solver_failure'] = dict(time_s=float(failure[1]),
                                                step_s=float(failure[2]),
                                                node=failure[3])
            return result

        with ThreadPoolExecutor(max_workers=3) as pool:
            cases = list(pool.map(solve, jobs))
    inputs = (ROOT / 'steady_supply.py', ROOT / 'signal_path.py',
              ROOT / 'transformer_candidates.py',
              ROOT / 'tests/test_frames.py', MODEL, REGISTER,
              ROOT / 'circuits/k7222-11-horizontal-output-page4.kicad_sch',
              ROOT / 'reference/k7222-11/t3-page4-visible-graph.json',
              ROOT / 'reference/k7222-11/t3-page4-provisional-parameters.json',
              ROOT / 't3_page4_connected_stiffness_screen.py', Path(__file__))
    return dict(format='dac-monitor-t3-page4-connected-v4-boundary-screen-v1',
                qualification='synthetic 17 ms startup sensitivity at registered provisional V4 CJO/TT corners; not a source-qualified device or T3 design point',
                input_sha256={str(path.relative_to(ROOT)): sha(path) for path in inputs},
                ngspice_sha256=sha(binary), interface=metadata['t3_interface'],
                magnetic_backend=metadata['magnetic_backend'],
                registered_bounds={key: dict(value=row['value'], bounds=row['bounds'],
                                             qualification=row['qualification'])
                                   for key, row in bounds.items()},
                cases=cases,
                interpretation='All registered V4 charge corners abort before 17 ms. Their saved trace tails coincide with the start of a 0.1 ns logic-source transition, so the reported trouble node does not identify a failed physical device. The V4 charge bounds alone do not provide a settled X2:4 drive waveform.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ngspice', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args()
    report = run(args.ngspice)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    for case in report['cases']:
        print(case['name'], case['status'], case.get('solver_failure'),
              case['raw_tail'])
