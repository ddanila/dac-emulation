"""Test horizontal coupling and Q201 as causes of the 39 ms stop.

These are one-factor diagnostics of an archived connected deck, not
source-circuit corrections or evidence of a sustained operating point.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path

import steady_supply
import t3_field_boundary_screen as boundary


ROOT = Path(__file__).resolve().parent
CHANGES = {
    'feedback_open': (
        'C1012 h_pdreturn h_feedback 1e-07',
        'C1012 h_pdreturn 0 1e-07',
        'T3 feedback disconnected from the horizontal phase detector at C1012.'),
    'sync_open': (
        'C1008 h_pd sync_c 6.8e-09',
        'C1008 h_pd 0 6.8e-09',
        'Input sync disconnected from the horizontal phase detector at C1008.'),
    'q201_off': (
        'Q201 contrast_low base_i 0 SC60A_CLASS_N',
        'R201_off contrast_low 0 1G',
        'Nearly off Q201 replaced by a 1 Gohm collector-to-emitter path.'),
    'q201_linear_off': (
        'Q201 contrast_low base_i 0 SC60A_CLASS_N',
        'R201_off contrast_low 0 1G\nC201_be base_i 0 10p\nC201_bc contrast_low base_i 4p',
        'Nearly off Q201 replaced by a 1 Gohm path and its stated 10 pF BE / 4 pF BC zero-bias capacitances as linear elements.'),
    'q201_be_only': (
        'Q201 contrast_low base_i 0 SC60A_CLASS_N',
        'R201_off contrast_low 0 1G\nC201_be base_i 0 10p',
        'Nearly off Q201 replaced by a 1 Gohm path and 10 pF linear BE capacitance only.'),
    'q201_bc_only': (
        'Q201 contrast_low base_i 0 SC60A_CLASS_N',
        'R201_off contrast_low 0 1G\nC201_bc contrast_low base_i 4p',
        'Nearly off Q201 replaced by a 1 Gohm path and 4 pF linear BC capacitance only.'),
    'q201_cjc_low': (
        'Q201 contrast_low base_i 0 SC60A_CLASS_N',
        'Q201 contrast_low base_i 0 SC60A_Q201_CJC_LOW_N',
        'Q201 alone retains the BJT model with CJC reduced from 4 to its registered 1.7 pF lower bound.'),
}

Q201_MODEL = '.model SC60A_CLASS_N NPN(IS=1e-14 BF=260 VAF=80 RC=1 RE=0.25 CJE=10p CJC=4p TF=0.8n TR=10n IKF=0.0962 RB=100 VJE=0.65 MJE=0.55 VJC=0.65 MJC=0.33 EG=1.11 XTI=3 FC=0.5)'


def run_case(name, baseline, output, runtime, timeout_s):
    old, new, description = CHANGES[name]
    if baseline.count(old) != 1:
        raise ValueError(name + ': baseline connection changed')
    deck = baseline.replace(old, new)
    if name == 'q201_cjc_low':
        if deck.count(Q201_MODEL) != 1:
            raise ValueError('Q201 source model changed')
        bounded = Q201_MODEL.replace('SC60A_CLASS_N', 'SC60A_Q201_CJC_LOW_N', 1)
        bounded = bounded.replace('CJC=4p', 'CJC=1.7p')
        deck = deck.replace(Q201_MODEL, Q201_MODEL+'\n'+bounded)
    directory = output/name
    if directory.exists():
        if (directory/'run.cir').read_text() != deck:
            raise ValueError(name + ': existing deck differs from declared edit')
        result = json.loads((directory/'solve.json').read_text())
    else:
        result = steady_supply.solve(deck, directory, runtime, timeout_s=timeout_s)
    rows, last_time = boundary.raw_tail(directory/'trace.raw')
    log = (directory/'solver.log').read_text(errors='replace')
    return {
        'name': name, 'change': description,
        'deck_sha256': boundary.sha(directory/'run.cir'),
        'raw_sha256': boundary.sha(directory/'trace.raw'),
        'solver_log_sha256': boundary.sha(directory/'solver.log'),
        'solve_status': result['status'], 'solve_elapsed_s': result['elapsed_s'],
        'solve_timeout': result['timeout'], 'raw_complete_rows': rows,
        'last_time_s': last_time, 'crossed_39_ms': last_time > .039,
        'solver_warnings': [line.strip() for line in log.replace('\r', '\n').splitlines()
                            if line.startswith('Warning:')],
        'solver_abort_messages': [line.strip() for line in log.replace('\r', '\n').splitlines()
                                  if 'Timestep too small' in line or
                                  'run simulation(s) aborted' in line],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--timeout-s', type=float, default=900)
    args = parser.parse_args()
    baseline = args.baseline.read_text()
    if baseline.count(boundary.SHORT_TRAN) != 1 or baseline.count('.options klu reltol=0.005') != 1:
        raise ValueError('expected archived 39.1 ms KLU deck')
    args.output.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=2) as pool:
        pending = {name: pool.submit(run_case, name, baseline, args.output,
                                     args.runtime, args.timeout_s)
                   for name in CHANGES}
        cases = [pending[name].result() for name in CHANGES]
    report = {
        'format': 'dac-monitor-t3-horizontal-boundary-isolation-v5',
        'qualification': 'one-factor solver diagnosis; no edit is a source-circuit correction or a sustained field',
        'source_sha256': {
            'producer': boundary.sha(ROOT/'t3_horizontal_boundary_isolation.py'),
            'steady_supply.py': boundary.sha(ROOT/'steady_supply.py'),
        },
        'baseline_deck_sha256': boundary.sha(args.baseline),
        'baseline_last_time_s': boundary.raw_tail(args.baseline.parent/'trace.raw')[1],
        'cases': cases,
    }
    args.report.write_text(json.dumps(report, indent=2)+'\n')
    print(args.report)


if __name__ == '__main__':
    main()
