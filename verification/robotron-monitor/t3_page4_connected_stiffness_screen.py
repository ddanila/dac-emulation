"""Screen solver and logic-edge sensitivity of a provisional connected T3."""

from concurrent.futures import ThreadPoolExecutor
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import struct
import subprocess
import sys
import tempfile
import time

import signal_path
import steady_supply
import transformer_candidates


ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / 'reference/k7222-11/t3-page4-connected-stiffness-screen.json'
sys.path.insert(0, str(ROOT / 'tests'))
from test_frames import capture  # Explicit synthetic diagnostic input.


CASES = (
    ('klu_gear', 'klu', 'gear', 0.1, 120),
    ('sparse_trap', 'sparse', 'trap', 0.1, 120),
    ('edge20ns', 'sparse', 'gear', 20, 120),
    ('edge100ns', 'sparse', 'gear', 100, 150),
)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def finite_edge_pwl(edge_s):
    def pwl(events, channel, hz, stop):
        last = events[0][channel]
        points = [f'0 {last}']
        for row in events[1:]:
            t = row[0] / hz
            if t > stop:
                break
            value = row[channel]
            if value != last:
                points.extend((f'{max(0, t - edge_s):.15g} {last}',
                               f'{t:.15g} {value}'))
                last = value
        return 'PWL(' + ' '.join(points) + ')'
    return pwl


def raw_tail(path):
    if not path.exists():
        return None
    with path.open('rb') as stream:
        header = b''
        while not header.endswith(b'Binary:\n'):
            line = stream.readline()
            if not line or len(header) > 1000000:
                return None
            header += line
        count = int(re.search(rb'No. Variables:\s+(\d+)', header)[1])
        declared = int(re.search(rb'No. Points:\s+(\d+)', header)[1])
        data = stream.read()
    width = count * 8
    rows = len(data) // width
    if not rows or len(data) % width:
        return None
    last_time = struct.unpack_from('=d', data, (rows - 1) * width)[0]
    if not math.isfinite(last_time):
        raise ValueError('nonfinite raw tail time')
    return dict(rows=rows, declared_rows=declared, last_time_s=last_time,
                complete_header=declared == rows)


def run(ngspice):
    binary = Path(ngspice).resolve()
    with tempfile.TemporaryDirectory() as directory:
        scratch = Path(directory)
        assembly = steady_supply.assemble(
            scratch / 'assembly', t3_interface='page4-visible-20-port')
        candidate = transformer_candidates.enumerate_candidates(
            assembly['magnetic_graph'])[0]
        selection = steady_supply.select(capture())
        original_pwl = signal_path.pwl
        jobs = []
        try:
            for name, solver, method, edge_ns, timeout_s in CASES:
                signal_path.pwl = (original_pwl if edge_ns == 0.1 else
                                   finite_edge_pwl(edge_ns * 1e-9))
                deck, metadata = steady_supply.deck(
                    assembly, selection, candidate, magnetic_backend='coupled',
                    max_step_s=50e-9)
                case_dir = scratch / name
                case_dir.mkdir()
                lines = []
                for line in deck.splitlines():
                    if line.startswith('.options '):
                        line = (f'.options {solver} reltol=0.005 abstol=1e-6 '
                                f'vntol=1e-6 method={method}')
                    elif line.startswith('.save '):
                        line = ('.save time v(eht) v(h_hot) v(h_return) '
                                'v(h_boost) v(p41) i(Lhorizontal) '
                                'v(h_outputbase) v(h_drivecol)')
                    elif line.startswith('.tran '):
                        line = '.tran 50n 17ms 16ms 50n'
                    lines.append(line)
                circuit = '\n'.join(lines) + '\n'
                (case_dir / 'run.cir').write_text(circuit)
                jobs.append((name, solver, method, edge_ns, timeout_s,
                             case_dir, hashlib.sha256(circuit.encode()).hexdigest()))
        finally:
            signal_path.pwl = original_pwl

        def solve(job):
            name, solver, method, edge_ns, timeout_s, case_dir, deck_hash = job
            started = time.monotonic()
            try:
                process = subprocess.run(
                    [str(binary), '-b', '-r', 'trace.raw', '-o', 'solver.log',
                     'run.cir'], cwd=case_dir, capture_output=True, text=True,
                    timeout=timeout_s)
                code = process.returncode
                status = 'complete' if code == 0 else 'aborted'
            except subprocess.TimeoutExpired:
                code = None
                status = 'timeout'
            log_path = case_dir / 'solver.log'
            log = log_path.read_text() if log_path.exists() else ''
            failure = re.search(
                r'Timestep too small; time = ([\d.e+-]+), '
                r'timestep = ([\d.e+-]+): trouble with node "([^"]+)"', log)
            if status == 'aborted' and failure is None:
                raise ValueError(f'{name} failed without classified solver error')
            result = dict(name=name, linear_solver=solver, integration=method,
                          source_edge_ns=edge_ns, stop_ms=17, saved_from_ms=16,
                          max_step_ns=50, timeout_s=timeout_s, status=status,
                          returncode=code, elapsed_s=round(time.monotonic()-started, 3),
                          deck_sha256=deck_hash,
                          solver_log_sha256=sha(log_path) if log_path.exists() else None,
                          raw_tail=raw_tail(case_dir / 'trace.raw'))
            if failure:
                result['solver_failure'] = dict(
                    time_s=float(failure[1]), step_s=float(failure[2]),
                    node=failure[3])
            return result

        with ThreadPoolExecutor(max_workers=4) as pool:
            cases = list(pool.map(solve, jobs))
    inputs = (ROOT / 'steady_supply.py', ROOT / 'signal_path.py',
              ROOT / 'transformer_candidates.py', ROOT / 'tests/test_frames.py',
              ROOT / 'circuits/signal-path-models.cir',
              ROOT / 'circuits/k7222-11-horizontal-output-page4.kicad_sch',
              ROOT / 'reference/k7222-11/t3-page4-visible-graph.json',
              ROOT / 'reference/k7222-11/t3-page4-provisional-parameters.json',
              Path(__file__))
    return dict(format='dac-monitor-t3-page4-connected-stiffness-screen-v1',
                qualification='synthetic 17 ms startup sensitivity only; no source-bounded input edge, periodic state, or selected T3 ratio',
                input_sha256={str(path.relative_to(ROOT)): sha(path)
                              for path in inputs},
                ngspice_sha256=sha(binary),
                interface=metadata['t3_interface'],
                magnetic_backend=metadata['magnetic_backend'],
                cases=cases,
                interpretation='Changing the linear solver, integration method, or assumed input edge did not produce a qualified 17 ms connected trace in these bounded trials. Timeout is not a solver abort; all outcomes remain startup diagnostics.')


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
