"""Compare pre-bridge and corrected T3 graphs in the same connected startup."""
from concurrent.futures import ThreadPoolExecutor
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

import signal_path
import steady_supply
import transformer_candidates as tc
import t3_page4_upper_bridge_candidate as corrected
import t3_page4_connected_input_skew_screen as skew
from t3_page4_connected_drive_diagnostic import trace_rows

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / 'reference/k7222-11/t3-page4-upper-bridge-screen.json'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(ngspice, work, source_pdf):
    work = Path(work).resolve()
    work.mkdir(parents=True, exist_ok=False)
    binary = Path(ngspice).resolve()
    assemblies = {
        'pre_bridge': steady_supply.assemble(work / 'pre_bridge/assembly', t3_interface='page4-visible-20-port'),
        'upper_bridge': corrected.assemble(work / 'upper_bridge/assembly', source_pdf),
    }
    jobs = []
    selection = steady_supply.select(skew.capture())
    original = signal_path.pwl
    try:
        signal_path.pwl = skew.skewed_pwl(original, 1)
        for name, assembly in assemblies.items():
            candidate = tc.enumerate_candidates(assembly['magnetic_graph'])[0]
            deck, metadata = steady_supply.deck(assembly, selection, candidate,
                                                magnetic_backend='coupled', max_step_s=50e-9)
            lines = []
            for line in deck.splitlines():
                if line.startswith('.tran '):
                    line = '.tran 50n 20ms 19ms 50n'
                elif line.startswith('.save '):
                    line = '.save time v(eht) v(h_hot) v(h_return) v(h_boost) v(p41) v(h_sync) i(Lhorizontal)'
                lines.append(line)
            if name == 'upper_bridge':
                lines[0] += '; corrected X1:1-X1:7 wire and split HV/upper graph'
                metadata['upper_bridge_correction'] = assembly['upper_bridge_correction']
            path = work / name
            (path / 'run.cir').write_text('\n'.join(lines) + '\n')
            (path / 'metadata.json').write_text(json.dumps(metadata, indent=2) + '\n')
            jobs.append((name, path, candidate, assembly['hashes']))
    finally:
        signal_path.pwl = original

    def solve(job):
        name, path, candidate, hashes = job
        print('solving ' + name, flush=True)
        try:
            process = subprocess.run([str(binary), '-b', '-r', 'trace.raw', '-o',
                                      'solver.log', 'run.cir'], cwd=path,
                                     capture_output=True, text=True, timeout=180)
            status = 'complete' if process.returncode == 0 else 'aborted'
        except subprocess.TimeoutExpired:
            status = 'timeout'
        log = (path / 'solver.log').read_text()
        result = dict(name=name, status=status, candidate=candidate,
                      deck_sha256=sha(path / 'run.cir'),
                      solver_log_sha256=sha(path / 'solver.log'),
                      assembly_inputs_sha256=hashes)
        if status == 'complete':
            result['observed'] = skew.summarize(trace_rows(path / 'trace.raw'), 20, 19)
        else:
            failure = re.search(r'Timestep too small; time = ([\d.e+-]+), timestep = ([\d.e+-]+): trouble with node "([^"]+)"', log)
            result['solver_failure'] = (dict(time_s=float(failure[1]), step_s=float(failure[2]), node=failure[3])
                                        if failure else log[-2000:])
        return result

    with ThreadPoolExecutor(max_workers=2) as pool:
        cases = list(pool.map(solve, jobs))
    return dict(
        format='dac-monitor-t3-page4-upper-bridge-screen-v1',
        qualification='paired connected startup under provisional section parameters and unverified 1 ns BSYN delay; no periodic state, installed winding or A5 qualification',
        ngspice_sha256=sha(binary), source_pdf_sha256=sha(source_pdf),
        artifact_directory=os.path.relpath(work, ROOT.parents[1]),
        script_sha256=sha(__file__), correction_script_sha256=sha(corrected.__file__),
        correction=assemblies['upper_bridge']['upper_bridge_correction'],
        setup=dict(stop_ms=20, saved_from_ms=19, max_step_ns=50, bsyn_delay_ns=1,
                   source='synthetic diagnostic capture', polarity='all positive relative group signs; split upper group adds independent untested sign',
                   timeout_s=180),
        cases=cases, a5_qualified=False,
        limitations=['The same provisional numerical sections are retained except for the removed X1:1-X1:2 one-turn bridge.',
                     'Only the separated HV overwind receives the reduced overwind coupling; upper taps now use background coupling.',
                     'The two graph candidates differ in external join, section map and resulting coupling. This is a topology correction, not a one-parameter sensitivity.',
                     'Remaining polarity alternatives, section bounds, periodicity and timestep convergence must be checked before selecting a design point.'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ngspice', type=Path, required=True)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--source-pdf', type=Path, default=ROOT.parents[1] / 'build/monitor/phase-a/sources/older.pdf')
    parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args()
    report = run(args.ngspice, args.work, args.source_pdf)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    for case in report['cases']:
        print(case['name'], case['status'], case.get('observed', case.get('solver_failure')))
