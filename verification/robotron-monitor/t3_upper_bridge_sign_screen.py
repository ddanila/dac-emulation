"""Screen G1-compatible corrected T3 signs in the connected 20 ms startup."""
from concurrent.futures import ThreadPoolExecutor
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

import signal_path
import steady_supply
import transformer_candidates as tc
import t3_page4_upper_bridge_candidate as upper
import t3_page4_connected_input_skew_screen as skew
from t3_page4_connected_drive_diagnostic import trace_rows

ROOT = Path(__file__).resolve().parent
REF = ROOT / 'reference/k7222-11'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(ngspice, work, source_pdf):
    work = Path(work).resolve()
    work.mkdir(parents=True, exist_ok=False)
    binary = Path(ngspice).resolve()
    sign_report = json.loads((REF / 't3-upper-bridge-g1-sign.json').read_text())
    if not sign_report['passed'] or sign_report['qualified_g1_sign'] is not None:
        raise ValueError('G1 sign report is no longer conditional or passed')
    assembly = upper.assemble(work / 'assembly', source_pdf)
    candidates = tc.enumerate_candidates(assembly['magnetic_graph'])
    accepted = set(sign_report['conditionally_accepted_ids'])
    if len(accepted) != 8 or {c['id'] for c in candidates if c['id'] in accepted} != accepted:
        raise ValueError('G1 sign report does not match corrected graph')
    selection = steady_supply.select(skew.capture())
    original = signal_path.pwl
    jobs = []
    try:
        signal_path.pwl = skew.skewed_pwl(original, 1)
        for candidate in candidates:
            if candidate['id'] not in accepted:
                continue
            deck, metadata = steady_supply.deck(assembly, selection, candidate,
                                                magnetic_backend='coupled', max_step_s=50e-9)
            lines = []
            for line in deck.splitlines():
                if line.startswith('.tran '):
                    line = '.tran 50n 20ms 19ms 50n'
                elif line.startswith('.save '):
                    line = '.save time v(eht) v(h_hot) v(h_return) v(h_boost) v(p41) v(h_sync) i(Lhorizontal)'
                lines.append(line)
            path = work / candidate['id']
            path.mkdir()
            (path / 'run.cir').write_text('\n'.join(lines) + '\n')
            (path / 'metadata.json').write_text(json.dumps(metadata, indent=2) + '\n')
            jobs.append((path, candidate))
    finally:
        signal_path.pwl = original

    def solve(job):
        path, candidate = job
        try:
            process = subprocess.run([str(binary), '-b', '-r', 'trace.raw', '-o',
                                      'solver.log', 'run.cir'], cwd=path,
                                     capture_output=True, text=True, timeout=300)
            status = 'complete' if process.returncode == 0 else 'aborted'
        except subprocess.TimeoutExpired:
            status = 'timeout'
        log = (path / 'solver.log').read_text()
        row = dict(candidate_id=candidate['id'], polarity=candidate['polarity'],
                   status=status, deck_sha256=sha(path / 'run.cir'),
                   solver_log_sha256=sha(path / 'solver.log'))
        if status == 'complete':
            row['observed'] = skew.summarize(trace_rows(path / 'trace.raw'), 20, 19)
        else:
            failure = re.search(r'Timestep too small; time = ([\d.e+-]+), timestep = ([\d.e+-]+): trouble with node "([^"]+)"', log)
            row['failure'] = (dict(time_s=float(failure[1]), step_s=float(failure[2]), node=failure[3])
                              if failure else log[-1000:])
        return row

    with ThreadPoolExecutor(max_workers=4) as pool:
        cases = list(pool.map(solve, jobs))
    return dict(format='dac-monitor-t3-upper-bridge-sign-screen-v1',
                qualification='conditional connected startup, not periodic or source-qualified winding sign',
                source_pdf_sha256=sha(source_pdf), ngspice_sha256=sha(binary),
                script_sha256=sha(__file__), correction_script_sha256=sha(upper.__file__),
                g1_report_sha256=sha(REF / 't3-upper-bridge-g1-sign.json'),
                assembly_hashes=assembly['hashes'],
                setup=dict(stop_ms=20, saved_from_ms=19, max_step_ns=50,
                           bsyn_delay_ns=1, source='synthetic diagnostic capture',
                           parameter_status='provisional', timeout_s=300),
                cases=cases, a5_qualified=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ngspice', type=Path, required=True)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--source-pdf', type=Path, default=ROOT.parents[1] / 'build/monitor/phase-a/sources/older.pdf')
    parser.add_argument('--output', type=Path, default=REF / 't3-upper-bridge-sign-screen.json')
    args = parser.parse_args()
    report = run(args.ngspice, args.work, args.source_pdf)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    for case in report['cases']:
        print(case['candidate_id'], case['status'], case.get('observed', case.get('failure')), flush=True)
