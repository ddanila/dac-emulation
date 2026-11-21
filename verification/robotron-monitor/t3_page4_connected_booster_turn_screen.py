"""Screen provisional T3 booster turns in the connected 20-port stage."""

from concurrent.futures import ThreadPoolExecutor
import argparse
import copy
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
OUTPUT = ROOT / 'reference/k7222-11/t3-page4-connected-booster-turn-screen.json'
SKEW_REPORT = skew.OUTPUT
FACTORS = (.25, .5, 1, 2, 4)
sys.path.insert(0, str(ROOT / 'tests'))
from test_frames import capture  # Explicit synthetic diagnostic input.


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def varied_parameters(assembly, factor):
    graph = assembly['magnetic_graph']
    drive = next(group for group in graph['groups'] if group['id'] == 'drive')
    if drive['taps'] != ['X2_7', 'X2_13', 'X2_11', 'X2_12', 'X2_10', 'X2_4']:
        raise ValueError('corrected visible booster order changed')
    parameters = copy.deepcopy(assembly['magnetic_parameters'])
    sections = parameters['groups']['drive']
    for index in (1, 2, 3):
        turns = sections[index]['turns']
        if turns['value'] != 7 or not turns['minimum'] <= 7*factor <= turns['maximum']:
            raise ValueError('booster section or registered bound changed')
        turns['value'] = 7 * factor
        turns['rationale'] = (f'Conditional {factor:g}x common booster-section '
                              'turns screen; no K7222.11 winding measurement.')
    return parameters


def run(ngspice):
    binary = Path(ngspice).resolve()
    prior = json.loads(SKEW_REPORT.read_text())
    if prior['format'] != 'dac-monitor-t3-page4-connected-input-skew-screen-v1':
        raise ValueError('connected skew baseline changed')
    for name, digest in prior['input_sha256'].items():
        if sha(ROOT / name) != digest:
            raise ValueError(f'connected skew input stale: {name}')
    if sha(binary) != prior['ngspice_sha256']:
        raise ValueError('connected skew solver changed')
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
        original_parameters = assembly['magnetic_parameters']
        original_pwl = signal_path.pwl
        jobs = []
        try:
            signal_path.pwl = skew.skewed_pwl(original_pwl, 1)
            for factor in FACTORS:
                assembly['magnetic_parameters'] = varied_parameters(
                    dict(assembly, magnetic_parameters=original_parameters), factor)
                deck, metadata = steady_supply.deck(
                    assembly, selection, candidate, magnetic_backend='coupled',
                    max_step_s=50e-9)
                case_dir = scratch / f'factor_{factor:g}'
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
                jobs.append((factor, case_dir,
                             hashlib.sha256(circuit.encode()).hexdigest()))
        finally:
            assembly['magnetic_parameters'] = original_parameters
            signal_path.pwl = original_pwl

        def solve(job):
            factor, case_dir, digest = job
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
                raise ValueError(f'{factor:g}x booster failed without classified solver error')
            result = dict(factor=factor, section_turns=7*factor,
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

        with ThreadPoolExecutor(max_workers=4) as pool:
            cases = list(pool.map(solve, jobs))
    nominal = next(row for row in cases if row['factor'] == 1)
    if nominal['status'] != 'complete' or nominal['observed'] != baseline['observed']:
        raise ValueError('connected booster nominal differs from saved two-period baseline')
    inputs = (SKEW_REPORT, ROOT / 'steady_supply.py', ROOT / 'signal_path.py',
              ROOT / 'transformer_candidates.py', ROOT / 'tests/test_frames.py',
              ROOT / 'reference/k7222-11/t3-page4-provisional-parameters.json',
              ROOT / 'reference/k7222-11/t3-page4-visible-graph.json',
              ROOT / 't3_page4_connected_input_skew_screen.py',
              ROOT / 't3_page4_connected_drive_diagnostic.py',
              ROOT / 't3_page4_connected_stiffness_screen.py', Path(__file__))
    return dict(format='dac-monitor-t3-page4-connected-booster-turn-screen-v1',
                qualification='five conditional connected two-period booster-section sensitivities within assumed turn bounds; 1 ns unverified BSYN skew and provisional T3 graph; no installed ratio or periodic qualification',
                input_sha256={str(path.relative_to(ROOT)): sha(path) for path in inputs},
                ngspice_sha256=sha(binary), interface=metadata['t3_interface'],
                candidate_id=candidate['id'], stop_ms=stop_ms,
                saved_from_ms=save_from_ms, factors=list(FACTORS), cases=cases)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ngspice', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args()
    report = run(args.ngspice)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    for case in report['cases']:
        print(case['factor'], case['status'],
              case.get('observed', case.get('solver_failure')), flush=True)
