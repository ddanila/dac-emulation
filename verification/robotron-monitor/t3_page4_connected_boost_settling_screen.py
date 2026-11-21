"""Compare two C21 starts in the conditional connected 20-port T3 stage."""

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

import signal_path
import steady_supply
import transformer_candidates
import t3_page4_connected_input_skew_screen as skew
from t3_page4_connected_drive_diagnostic import trace_rows
from t3_page4_connected_stiffness_screen import raw_tail


ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / 'reference/k7222-11/t3-page4-connected-boost-settling-screen.json'
SKEW_REPORT = skew.OUTPUT
sys.path.insert(0, str(ROOT / 'tests'))
from test_frames import capture  # Explicit synthetic diagnostic input.


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(ngspice):
    binary = Path(ngspice).resolve()
    prior = json.loads(SKEW_REPORT.read_text())
    if prior['format'] != 'dac-monitor-t3-page4-connected-input-skew-screen-v1':
        raise ValueError('connected input-skew baseline changed')
    for name, digest in prior['input_sha256'].items():
        if sha(ROOT / name) != digest:
            raise ValueError(f'connected input-skew input stale: {name}')
    if sha(binary) != prior['ngspice_sha256']:
        raise ValueError('connected input-skew solver changed')
    baseline = next(row for row in prior['cases']
                    if row['bsyn_skew_ns'] == 1 and row['stop_ms'] > 40)
    with tempfile.TemporaryDirectory() as directory:
        scratch = Path(directory)
        assembly = steady_supply.assemble(
            scratch / 'assembly', t3_interface='page4-visible-20-port')
        candidate = transformer_candidates.enumerate_candidates(
            assembly['magnetic_graph'])[0]
        selection = steady_supply.select(capture())
        stop_ms = 2000 * selection['period_ticks'] / selection['clock_hz']
        save_from_ms = stop_ms - 1
        original_pwl = signal_path.pwl
        try:
            signal_path.pwl = skew.skewed_pwl(original_pwl, 1)
            plain, metadata = steady_supply.deck(
                assembly, selection, candidate, magnetic_backend='coupled',
                max_step_s=50e-9)
            rail_line = next(line for line in plain.splitlines()
                             if line.startswith('Vp41 p41 0 '))
            rail_v = float(rail_line.split()[-1])
            initial_boost_v = rail_v + 65
            warm, _ = steady_supply.deck(
                assembly, selection, candidate, magnetic_backend='coupled',
                max_step_s=50e-9,
                initial_voltages={'h_boost': initial_boost_v})
            if (f'.ic v(h_boost)={initial_boost_v:.15g}' not in warm or
                    '.ic v(h_boost)=' in plain):
                raise ValueError('paired C21 initial-condition decks changed')
        finally:
            signal_path.pwl = original_pwl
        jobs = []
        for name, initial_c21_v, deck in (
                ('unseeded', None, plain), ('c21_65v', 65, warm)):
            case_dir = scratch / name
            case_dir.mkdir()
            lines = []
            for line in deck.splitlines():
                if line.startswith('.save '):
                    line = ('.save time v(eht) v(h_hot) v(h_return) '
                            'v(h_boost) v(p41) v(h_sync) i(Lhorizontal)')
                elif line.startswith('.tran '):
                    line = f'.tran 50n {stop_ms:.15g}ms {save_from_ms:.15g}ms 50n'
                lines.append(line)
            circuit = '\n'.join(lines) + '\n'
            (case_dir / 'run.cir').write_text(circuit)
            jobs.append((name, initial_c21_v, case_dir,
                         hashlib.sha256(circuit.encode()).hexdigest()))

        def solve(job):
            name, initial_c21_v, case_dir, digest = job
            started = time.monotonic()
            try:
                process = subprocess.run(
                    [str(binary), '-b', '-r', 'trace.raw', '-o', 'solver.log',
                     'run.cir'], cwd=case_dir, capture_output=True, text=True,
                    timeout=300)
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
            result = dict(name=name, initial_c21_v=initial_c21_v,
                          status=status, returncode=code, timeout_s=300,
                          elapsed_s=round(time.monotonic()-started, 3),
                          deck_sha256=digest,
                          solver_log_sha256=sha(log_path) if log_path.exists() else None,
                          raw_tail=raw_tail(case_dir / 'trace.raw'))
            if failure:
                result['solver_failure'] = dict(time_s=float(failure[1]),
                                                step_s=float(failure[2]),
                                                node=failure[3])
            if status == 'complete':
                result['observed'] = skew.summarize(
                    trace_rows(case_dir / 'trace.raw'), stop_ms, save_from_ms)
            return result

        with ThreadPoolExecutor(max_workers=2) as pool:
            cases = list(pool.map(solve, jobs))
    if cases[0]['status'] != 'complete' or cases[0]['observed'] != baseline['observed']:
        raise ValueError('unseeded two-period baseline differs from saved skew screen')
    inputs = (SKEW_REPORT, ROOT / 'steady_supply.py', ROOT / 'signal_path.py',
              ROOT / 'transformer_candidates.py', ROOT / 'tests/test_frames.py',
              ROOT / 't3_page4_connected_input_skew_screen.py',
              ROOT / 't3_page4_connected_drive_diagnostic.py',
              ROOT / 't3_page4_connected_stiffness_screen.py', Path(__file__))
    return dict(format='dac-monitor-t3-page4-connected-boost-settling-screen-v1',
                qualification='paired conditional two-period connected startup with 1 ns unverified BSYN skew and provisional T3; not periodic or source-qualified',
                input_sha256={str(path.relative_to(ROOT)): sha(path) for path in inputs},
                ngspice_sha256=sha(binary), interface=metadata['t3_interface'],
                candidate_id=candidate['id'], rail_v=rail_v,
                seeded_boost_node_v=initial_boost_v,
                stop_ms=stop_ms, saved_from_ms=save_from_ms,
                cases=cases)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ngspice', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args()
    report = run(args.ngspice)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    for case in report['cases']:
        print(case['name'], case['status'],
              case.get('observed', case.get('solver_failure')), flush=True)
