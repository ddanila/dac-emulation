"""Build a paired diagnostic candidate with the source-drawn upper T3 bridge.

Keep the pre-bridge graph and its numerical reports intact. This variant splits
the overwind from the upper tapped winding before joining X1:1 and X1:7.
All numerical section values remain provisional; this is not A5 closure.
"""
import copy
import hashlib
import json
from pathlib import Path
import subprocess

import page4_t3_upper_bridge_audit as audit
import page4_t3_visible_wrapper as wrapper
import steady_supply
import transformer_candidates as tc

ROOT = Path(__file__).resolve().parent
REF = ROOT / 'reference/k7222-11'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def corrected_graph_and_parameters(graph, parameters):
    graph, parameters = copy.deepcopy(graph), copy.deepcopy(parameters)
    hv = next(group for group in graph['groups'] if group['id'] == 'high_voltage')
    if hv['taps'] != ['X3_1', 'X1_1', 'X1_2', 'X1_3', 'X1_5', 'X1_7']:
        raise ValueError('pre-bridge HV graph changed; re-evaluate correction')
    sections = parameters['groups']['high_voltage']
    if len(sections) != 5 or [s['turns']['value'] for s in sections] != [1768, 1, 1, 3, 30]:
        raise ValueError('pre-bridge parameter transfer changed')
    upper = dict(id='upper_taps', taps=['X1_2', 'X1_3', 'X1_5', 'X1_7'],
                 evidence={'file': 'older.pdf', 'page': 4},
                 assumption='Separate upper tapped winding candidate; internal order and section values remain provisional. X1:7 is externally wired to the overwind end X1:1.')
    hv['taps'] = ['X3_1', 'X1_1']
    hv['assumption'] = 'Separate HV overwind candidate from V21 anode X3:1 to X1:1; X1:1 externally joins X1:7. Turns and manual connection 16 remain unqualified.'
    graph['groups'].insert(graph['groups'].index(hv) + 1, upper)
    graph['id'] = 'k7222-11-t3-page4-upper-bridge-candidate'
    graph['upper_bridge_source_sha256'] = sha(audit.SOURCE)
    graph['limitations'].append('X1:1-X1:7 is an external conductor. The prior assumed X1:1-X1:2 winding section is removed; the remaining section values are transferred hypotheses.')
    parameters['groups']['high_voltage'] = sections[:1]
    parameters['groups']['upper_taps'] = sections[2:]
    parameters['rationale'] = 'Upper-bridge diagnostic: separate HV and upper tapped groups; omit assumed X1:1-X1:2 section; retain all other provisional values without fitting.'
    parameters['source_basis']['page4_visible_transfer'] = (
        '1768 provisional turns on X3:1-X1:1; 1/3/30 provisional turns on '
        'X1:2-X1:3-X1:5-X1:7; X1:1-X1:7 is a direct external wire. '
        'The bridge has source evidence; section values and polarities do not.')
    tc.validate(graph)
    return graph, parameters


def assemble(out, source_pdf):
    checked = audit.run(source_pdf)
    if checked['source_model_match']:
        raise ValueError('base wrapper already includes the bridge; re-evaluate paired candidate')
    out = Path(out)
    assembly = steady_supply.assemble(out, t3_interface='page4-visible-20-port')
    graph, parameters = corrected_graph_and_parameters(
        assembly['magnetic_graph'], assembly['magnetic_parameters'])
    sheet = wrapper.replace_once(
        wrapper.candidate_sheet(), '(label "t3_x1_7" (at 135 475.4 0)',
        '(label "t3_x1_1" (at 135 475.4 0)')
    sheet_name = 'circuits/k7222-11-horizontal-output-upper-bridge.kicad_sch'
    sheet_path = out / sheet_name
    sheet_path.write_text(sheet)
    xml = out / 'horizontal-output-upper-bridge.xml'
    subprocess.run(['kicad-cli', 'sch', 'export', 'netlist', '--format',
                    'kicadxml', '-o', str(xml), str(sheet_path)],
                   check=True, capture_output=True, text=True)
    pins = wrapper.exported_pins(xml, '012-6921:T3')
    nodes = {port: pins[str(i)] for i, port in enumerate(wrapper.PORTS, 1)}
    base_xml = out / 'k7222-11-horizontal-output-page4.xml'
    others = lambda file: {key: value for key, value in wrapper.all_exported_pins(file).items()
                           if key[0] != 'X1136'}
    checks = {
        'same_20_ports': len(pins) == 20 and set(nodes) == {p for g in graph['groups'] for p in g['taps']},
        'upper_bridge_joined': nodes['X1_1'] == nodes['X1_7'],
        'upper_return_preserved': nodes['X1_2'] == nodes['X2_3'],
        'crossed_taps_not_joined': all(nodes[p] != nodes['X1_1'] for p in ('X1_2', 'X1_3', 'X1_5')),
        'other_components_unchanged': others(xml) == others(base_xml),
        'no_group_short_circuited': all(len({nodes[p] for p in g['taps']}) == len(g['taps']) for g in graph['groups']),
    }
    if not all(checks.values()):
        raise ValueError('upper-bridge export mismatch: ' + str(checks))
    t3 = next(part for part in assembly['components'] if part['source_id'] == '012-6921:T3')
    t3['nodes'] = [nodes[p] for group in graph['groups'] for p in group['taps']]
    assembly['magnetic_graph'], assembly['magnetic_parameters'] = graph, parameters
    for name, data in [('reference/k7222-11/t3-upper-bridge-graph.json', graph),
                       ('reference/k7222-11/t3-upper-bridge-parameters.json', parameters)]:
        (out / name).write_text(json.dumps(data, indent=2) + '\n')
        assembly['hashes'][name] = sha(out / name)
    assembly['hashes'][sheet_name] = sha(sheet_path)
    for source in (Path(__file__), audit.SOURCE):
        name = str(source.relative_to(ROOT))
        (out / name).write_bytes(source.read_bytes())
        assembly['hashes'][name] = sha(out / name)
    assembly['upper_bridge_correction'] = dict(
        checks=checks, exported_nodes=nodes, source_read_sha256=sha(audit.SOURCE),
        graph=graph, section_turns={name: [s['turns']['value'] for s in values]
                                   for name, values in parameters['groups'].items()},
        relative_polarity_candidates=len(tc.enumerate_candidates(graph)),
        a5_qualified=False)
    return assembly
