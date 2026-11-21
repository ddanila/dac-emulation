"""Trace the candidate T3 series path from EHT winding to external ground."""

import argparse
from collections import defaultdict, deque
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
REF = ROOT / 'reference/k7222-11'
GRAPH = REF / 't3-winding-hypothesis.json'
ASSEMBLY = REF / 'horizontal-output-transcription.json'
SOURCE = REF / 't3-series-return-source-read.json'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def candidate_path(graph, assembly):
    t3 = [part for part in assembly['components']
          if part['source_id'] == '012-6921:T3']
    if len(t3) != 1 or len(assembly['ports']) != len(t3[0]['nodes']):
        raise ValueError('T3 assembly ports are not unique and complete')
    nodes = dict(zip(assembly['ports'], t3[0]['nodes']))
    edges = defaultdict(list)

    def connect(a, b, kind):
        edges[a].append((b, kind))
        edges[b].append((a, kind))

    for port, node in nodes.items():
        connect(port, 'NET:' + node, 'external-net')
    for group in graph['groups']:
        for a, b in zip(group['taps'], group['taps'][1:]):
            if a not in nodes or b not in nodes:
                raise ValueError('winding tap is absent from T3 assembly')
            connect(a, b, 'winding:' + group['id'])

    start, target = 'X1_1', 'NET:0'
    queue = deque([(start, [start], [])])
    seen = {start}
    while queue:
        vertex, vertices, kinds = queue.popleft()
        if vertex == target:
            return nodes, vertices, kinds
        for next_vertex, kind in edges[vertex]:
            if next_vertex not in seen:
                seen.add(next_vertex)
                queue.append((next_vertex, vertices + [next_vertex], kinds + [kind]))
    return nodes, [], []


def run():
    graph = json.loads(GRAPH.read_text())
    assembly = json.loads(ASSEMBLY.read_text())
    source = json.loads(SOURCE.read_text())
    nodes, path, kinds = candidate_path(graph, assembly)
    required = {'X1_1', 'X1_16', 'X1_7', 'X1_3', 'X2_3', 'X2_5', 'NET:0'}
    expected_windings = {'winding:high_voltage', 'winding:upper_taps',
                         'winding:auxiliary'}
    if (nodes['X1_16'] == '0' or nodes['X2_5'] != '0'
            or nodes['X1_16'] != nodes['X1_7']
            or nodes['X1_3'] != nodes['X2_3']
            or not required <= set(path)
            or not expected_windings <= set(kinds)):
        raise ValueError('candidate series return differs from documented hypothesis')
    if source['format'] != 'dac-monitor-t3-series-return-source-read-v1':
        raise ValueError('unexpected series-return source read')
    return dict(
        format='dac-monitor-t3-series-return-audit-v1',
        qualification='candidate-graph DC-continuity check and cross-revision '
                      'repair comparator; no .11 internal-winding proof',
        inputs_sha256={str(path.relative_to(ROOT)): sha(path)
                       for path in (GRAPH, ASSEMBLY, SOURCE, Path(__file__))},
        source=source,
        candidate_port_nets={port: nodes[port] for port in
                             ('X1_1', 'X1_16', 'X1_7', 'X1_3', 'X2_3', 'X2_5')},
        x1_16_directly_grounded=nodes['X1_16'] == '0',
        eht_to_ground_path=path,
        path_edge_types=kinds,
        winding_groups_on_path=sorted({kind.removeprefix('winding:') for kind in kinds
                                       if kind.startswith('winding:')}),
        interpretation='The candidate has an EHT-to-ground DC winding chain '
                       'even though X1:16 is an ungrounded intermediate tap. '
                       'The repair statement that the footpoint is grounded '
                       'therefore cannot select the X1:16=0 variant. It is '
                       'compatible with a series-winding return but does not '
                       'prove the K7222.11 internal graph or polarity.',
        passed=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = run()
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(' -> '.join(result['eht_to_ground_path']))
