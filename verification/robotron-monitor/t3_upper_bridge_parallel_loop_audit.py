"""Audit the two source-wired parallel T3 paths in the corrected candidate."""
import hashlib
import json
from pathlib import Path
import tempfile

import t3_page4_upper_bridge_candidate as upper
import transformer_candidates as tc

ROOT = Path(__file__).resolve().parent
REF = ROOT / 'reference/k7222-11'
SOURCE = REF / 'page4-t3-internal-links-source-read.json'
SCREEN = REF / 't3-upper-bridge-sign-screen.json'
TP17 = REF / 't3-upper-bridge-tp17-assessment.json'
OUTPUT = REF / 't3-upper-bridge-parallel-loop-audit.json'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def path_data(graph, parameters, group_id, first, last):
    group = next(g for g in graph['groups'] if g['id'] == group_id)
    taps = group['taps']
    start, end = taps.index(first), taps.index(last)
    if end <= start:
        raise ValueError('parallel-path tap order changed')
    sections = parameters['groups'][group_id][start:end]
    return dict(group=group_id, taps=taps[start:end+1],
                section_turns=[s['turns']['value'] for s in sections],
                turns=sum(s['turns']['value'] for s in sections),
                resistance_ohm=sum(s['resistance_ohm']['value'] for s in sections),
                section_evidence=[s['turns']['evidence'] for s in sections])


def run(source_pdf):
    source = json.loads(SOURCE.read_text())
    if (source['source']['pdf_sha256'] != sha(source_pdf) or
            {tuple(pair) for pair in source['drawn_conductor_pairs']} !=
            {('X2_10', 'X1_15'), ('X2_11', 'X1_13')}):
        raise ValueError('lower T3 conductor source changed')
    screen, tp17 = json.loads(SCREEN.read_text()), json.loads(TP17.read_text())
    if not tp17['passed'] or tp17['screen_sha256'] != sha(SCREEN):
        raise ValueError('connected sign/TP17 evidence changed')
    with tempfile.TemporaryDirectory() as directory:
        assembly = upper.assemble(Path(directory) / 'assembly', source_pdf)
        graph, parameters = assembly['magnetic_graph'], assembly['magnetic_parameters']
        nodes = assembly['upper_bridge_correction']['exported_nodes']
        if not (nodes['X2_11'] == nodes['X1_13'] and
                nodes['X2_10'] == nodes['X1_15'] and
                nodes['X2_11'] != nodes['X2_10']):
            raise ValueError('source lower bridges absent from corrected export')
        drive = path_data(graph, parameters, 'drive', 'X2_11', 'X2_10')
        lower = path_data(graph, parameters, 'lower_taps', 'X1_13', 'X1_15')
        candidates = tc.enumerate_candidates(graph)
    cases = []
    by_id = {case['candidate_id']: case for case in screen['cases']}
    tp_by_id = {case['candidate_id']: case for case in tp17['cases']}
    if {c['id'] for c in candidates if c['id'] in by_id} != set(by_id):
        raise ValueError('connected signs do not match corrected graph')
    for candidate in candidates:
        observed = by_id.get(candidate['id'])
        if observed is None:
            continue
        signs = candidate['polarity']
        mismatch = drive['turns'] * signs['drive'] - lower['turns'] * signs['lower_taps']
        cases.append(dict(candidate_id=candidate['id'], lower_relative_sign=signs['lower_taps'],
                          assumed_loop_emf_turns=mismatch,
                          yoke_current_pp_a=observed['observed']['yoke_current_pp_a'],
                          tp17_swing_vpp=tp_by_id[candidate['id']]['tp17_swing_v'],
                          tp17_within_registered_band=tp_by_id[candidate['id']]['within_registered_band']))
    passed = (len(cases) == 8 and drive['turns'] == lower['turns'] == 14 and
              all(case['assumed_loop_emf_turns'] == 0 and case['tp17_within_registered_band']
                  if case['lower_relative_sign'] == 1 else
                  case['assumed_loop_emf_turns'] == 28 and not case['tp17_within_registered_band']
                  for case in cases))
    return dict(format='dac-monitor-t3-upper-bridge-parallel-loop-audit-v1',
                qualification='source external bridges plus provisional internal tap order and turns; not a factory winding map or A5 closure',
                source_read_sha256=sha(SOURCE), source_pdf_sha256=sha(source_pdf),
                correction_script_sha256=sha(upper.__file__), script_sha256=sha(__file__),
                connected_screen_sha256=sha(SCREEN), tp17_assessment_sha256=sha(TP17),
                external_bridges=source['drawn_conductor_pairs'],
                shared_endpoint_nets=[nodes['X2_11'], nodes['X2_10']],
                paths=[drive, lower],
                interpretation='With the candidate tap order, the two paths form a closed parallel winding loop. Matching phase and effective induced voltage are required; the registered 14/14 turns cancel loop EMF only for lower relative sign +1. A negative sign produces a 28-turn opposing loop under these provisional values.',
                cases=cases, qualified_lower_tap_sign=None,
                a5_qualified=False, passed=passed)


if __name__ == '__main__':
    source_pdf = ROOT.parents[1] / 'build/monitor/phase-a/sources/older.pdf'
    report = run(source_pdf)
    OUTPUT.write_text(json.dumps(report, indent=2) + '\n')
    print(f"parallel loop audit passed={report['passed']}; {len(report['cases'])} connected signs")
    raise SystemExit(0 if report['passed'] else 2)
