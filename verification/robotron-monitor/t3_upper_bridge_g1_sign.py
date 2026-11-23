"""Test the conditional G1 winding sign on the source-corrected T3 graph."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

import t3_page4_upper_bridge_candidate as upper
import transformer_candidates as candidates

ROOT = Path(__file__).resolve().parent
REF = ROOT / 'reference/k7222-11'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def pulse(graph, parameters, candidate, backend, directory):
    model, metadata = candidates.compile_model(graph, candidate, parameters, backend=backend)
    ports = metadata['ports']
    nodes = ['0' if port == 'X2_4' else port for port in ports]
    shunts = [f'Rref{i} {port} 0 1G' for i, port in enumerate(ports)
              if port not in ('X2_7', 'X2_4')]
    directory.mkdir()
    trace = directory / 'trace.txt'
    deck = directory / 'pulse.cir'
    deck.write_text('\n'.join([
        'Conditional T3 G1 sign; not a connected monitor run', model,
        'Vdrive X2_7 0 PULSE(0 1 20n 1n 1n 100n 200n)', *shunts,
        'Xtest ' + ' '.join(nodes) + ' T3_CANDIDATE',
        '.control', 'tran 1n 100n',
        f'wrdata {trace} v(X2_6,X2_5) v(X2_7)', 'quit', '.endc', '.end',
    ]) + '\n')
    solved = subprocess.run(['ngspice', '-b', str(deck)], capture_output=True, text=True)
    if solved.returncode or 'Error:' in solved.stdout + solved.stderr:
        raise ValueError('ngspice failed: ' + (solved.stdout + solved.stderr)[-1000:])
    rows = [list(map(float, line.split())) for line in trace.read_text().splitlines()
            if line.strip()]
    if not rows or any(len(row) != 4 for row in rows):
        raise ValueError('incomplete pulse trace')
    sample = min(rows, key=lambda row: abs(row[0] - 80e-9))
    if not 79e-9 <= sample[0] <= 81e-9 or sample[3] < .99:
        raise ValueError('drive pulse absent at 80 ns')
    return sample[1]


def run():
    graph, parameters = upper.corrected_graph_and_parameters(
        json.loads((REF / 't3-page4-visible-graph.json').read_text()),
        json.loads((REF / 't3-page4-provisional-parameters.json').read_text()))
    core = json.loads((REF / 't3-functional-core.json').read_text())
    assert core['functional_anchors']['v14_cathode_t3_terminal'] == 'X2:6'
    assert core['qualified_g1_relative_sign'] is None
    assert ['X2_5', 'X2_6'] == next(g['taps'][:2] for g in graph['groups'] if g['id'] == 'auxiliary')
    rows = []
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        for candidate in candidates.enumerate_candidates(graph):
            values = {backend: pulse(graph, parameters, candidate, backend,
                                     root / (candidate['id'] + '-' + backend))
                      for backend in ('xspice', 'flux')}
            rows.append(dict(id=candidate['id'], polarity=candidate['polarity'],
                             v_g1_xspice=values['xspice'], v_g1_flux=values['flux'],
                             conditionally_compatible=all(v < -.01 for v in values.values())))
    accepted = [row['id'] for row in rows if row['conditionally_compatible']]
    passed = (len(rows) == 16 and len(accepted) == 8 and
              all(row['polarity']['auxiliary'] == 1 for row in rows
                  if row['conditionally_compatible']) and
              all((row['v_g1_xspice'] < -.01) == (row['v_g1_flux'] < -.01) for row in rows))
    return dict(format='dac-monitor-t3-upper-bridge-g1-sign-v1',
                qualification='conditional isolated pulse only; X2:5 return and auxiliary continuity remain unverified',
                graph_source_sha256=sha(REF / 't3-page4-visible-graph.json'),
                parameters_source_sha256=sha(REF / 't3-page4-provisional-parameters.json'),
                functional_core_sha256=sha(REF / 't3-functional-core.json'),
                correction_script_sha256=sha(upper.__file__), script_sha256=sha(__file__),
                setup='1 V positive X2:7-to-X2:4 pulse, 1 Gohm shunts on other ports, V(X2:6)-V(X2:5) at 80 ns',
                assumptions=['X2:5 is the 00 return', 'X2:5 and X2:6 form the auxiliary winding',
                             'V14 must charge negative G1 on positive collector flyback'],
                candidate_results=rows, conditionally_accepted_ids=accepted,
                qualified_hv_sign=None, qualified_g1_sign=None, a5_qualified=False, passed=passed)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=REF / 't3-upper-bridge-g1-sign.json')
    args = parser.parse_args()
    report = run()
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(f"{len(report['conditionally_accepted_ids'])}/16 conditional G1 signs; passed={report['passed']}")
    raise SystemExit(0 if report['passed'] else 2)
