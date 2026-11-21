"""Probe simultaneous video/BSYN input edges in the connected 20-port stage."""

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
from t3_page4_connected_drive_diagnostic import trace_rows
from t3_page4_connected_stiffness_screen import raw_tail


ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / 'reference/k7222-11/t3-page4-connected-input-skew-screen.json'
SKEW_NS = (1, 5, 50)
sys.path.insert(0, str(ROOT / 'tests'))
from test_frames import capture  # Explicit synthetic diagnostic input.


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def skewed_pwl(original, skew_ns):
    def pwl(events, channel, hz, stop):
        if channel != 2:  # video and intensity retain the captured event ticks.
            return original(events, channel, hz, stop)
        last = events[0][channel]
        points = [f'0 {last}']
        for row in events[1:]:
            t = row[0] / hz + skew_ns * 1e-9
            if t > stop:
                break
            value = row[channel]
            if value != last:
                points.extend((f'{max(0, t - 1e-10):.15g} {last}',
                               f'{t:.15g} {value}'))
                last = value
        return 'PWL(' + ' '.join(points) + ')'
    return pwl


def summarize(rows, stop_ms, save_from_ms):
    if not rows or abs(rows[-1]['time'] - stop_ms * 1e-3) > 1e-9:
        raise ValueError('incomplete connected skew trace')
    duplicate_count = sum(a['time'] == b['time'] for a, b in zip(rows, rows[1:]))
    if any(a['time'] > b['time'] for a, b in zip(rows, rows[1:])):
        raise ValueError('connected skew trace time decreases')
    window = [row for row in rows if row['time'] >= save_from_ms * 1e-3]
    if len(window) < 1000:
        raise ValueError('insufficient connected skew trace samples')
    def bounds(values):
        return [min(values), max(values)]
    drive = [row['v(h_hot)'] - row['v(h_return)'] for row in window]
    c21 = [row['v(h_boost)'] - row['v(p41)'] for row in window]
    return dict(sample_count=len(window), duplicate_time_count=duplicate_count,
                window_s=[window[0]['time'], window[-1]['time']],
                eht_v=bounds([row['v(eht)'] for row in window]),
                hot_to_return_drive_v=bounds(drive),
                c21_differential_v=bounds(c21),
                tp17_mapped_v=bounds([row['v(h_sync)'] for row in window]),
                yoke_current_pp_a=(max(row['i(lhorizontal)'] for row in window) -
                                   min(row['i(lhorizontal)'] for row in window)),
                endpoint_eht_v=rows[-1]['v(eht)'],
                endpoint_c21_v=rows[-1]['v(h_boost)'] - rows[-1]['v(p41)'])


def run(ngspice):
    binary = Path(ngspice).resolve()
    with tempfile.TemporaryDirectory() as directory:
        scratch = Path(directory)
        assembly = steady_supply.assemble(
            scratch / 'assembly', t3_interface='page4-visible-20-port')
        candidate = transformer_candidates.enumerate_candidates(
            assembly['magnetic_graph'])[0]
        selection = steady_supply.select(capture())
        period_ms = 1000 * selection['period_ticks'] / selection['clock_hz']
        cases_to_run = [(skew_ns, 20, 19) for skew_ns in SKEW_NS]
        cases_to_run.append((1, 2 * period_ms, 2 * period_ms - 1))
        original_pwl = signal_path.pwl
        jobs = []
        try:
            for skew_ns, stop_ms, save_from_ms in cases_to_run:
                signal_path.pwl = skewed_pwl(original_pwl, skew_ns)
                deck, metadata = steady_supply.deck(
                    assembly, selection, candidate, magnetic_backend='coupled',
                    max_step_s=50e-9)
                case_dir = scratch / f'bsyn_{skew_ns}ns_{stop_ms:.3f}ms'
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
                jobs.append((skew_ns, stop_ms, save_from_ms, case_dir,
                             hashlib.sha256(circuit.encode()).hexdigest()))
        finally:
            signal_path.pwl = original_pwl

        def solve(job):
            skew_ns, stop_ms, save_from_ms, case_dir, digest = job
            started = time.monotonic()
            timeout_s = 300 if stop_ms > 30 else 180
            try:
                process = subprocess.run(
                    [str(binary), '-b', '-r', 'trace.raw', '-o', 'solver.log',
                     'run.cir'], cwd=case_dir, capture_output=True, text=True,
                    timeout=timeout_s)
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
                raise ValueError(f'{skew_ns} ns skew failed without classified solver error')
            result = dict(bsyn_skew_ns=skew_ns, stop_ms=stop_ms,
                          saved_from_ms=save_from_ms,
                          status=status, returncode=code,
                          timeout_s=timeout_s,
                          elapsed_s=round(time.monotonic()-started, 3),
                          deck_sha256=digest,
                          solver_log_sha256=sha(log_path) if log_path.exists() else None,
                          raw_tail=raw_tail(case_dir / 'trace.raw'))
            if failure:
                result['solver_failure'] = dict(time_s=float(failure[1]),
                                                step_s=float(failure[2]),
                                                node=failure[3])
            if status == 'complete':
                result['observed'] = summarize(trace_rows(case_dir / 'trace.raw'),
                                               stop_ms, save_from_ms)
            return result

        with ThreadPoolExecutor(max_workers=4) as pool:
            cases = list(pool.map(solve, jobs))
    inputs = (ROOT / 'steady_supply.py', ROOT / 'signal_path.py',
              ROOT / 'transformer_candidates.py', ROOT / 'tests/test_frames.py',
              ROOT / 'circuits/k7222-11-horizontal-output-page4.kicad_sch',
              ROOT / 'reference/k7222-11/t3-page4-visible-graph.json',
              ROOT / 'reference/k7222-11/t3-page4-provisional-parameters.json',
              ROOT / 't3_page4_connected_drive_diagnostic.py',
              ROOT / 't3_page4_connected_stiffness_screen.py', Path(__file__))
    return dict(format='dac-monitor-t3-page4-connected-input-skew-screen-v1',
                qualification='synthetic connected startup and two-period sensitivity with unverified BSYN timing offsets; no source-qualified input delay, periodic state or T3 ratio',
                input_sha256={str(path.relative_to(ROOT)): sha(path) for path in inputs},
                ngspice_sha256=sha(binary), interface=metadata['t3_interface'],
                magnetic_backend=metadata['magnetic_backend'],
                candidate_id=candidate['id'],
                capture_tick_ns=1e9 / selection['clock_hz'],
                capture_period_ms=period_ms,
                source_edge_ns=0.1,
                cases=cases)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ngspice', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args()
    report = run(args.ngspice)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    for case in report['cases']:
        print(case['bsyn_skew_ns'], case['status'],
              case.get('observed', case.get('solver_failure')), flush=True)
