"""Export a source-visible, non-numerical 20-port T3 KiCad wrapper candidate.

This leaves the active 19-port sheet intact. It changes only the T3 interface
and the source-contradicted external assignments, not its winding physics.
"""

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parent
REF = ROOT / 'reference/k7222-11'
SHEET = ROOT / 'circuits/k7222-11-horizontal-output.kicad_sch'
CANDIDATE_SHEET = ROOT / 'circuits/k7222-11-horizontal-output-page4.kicad_sch'
SOURCE = REF / 'page4-t3-terminal-identity-source-read.json'
GRAPH = REF / 't3-page4-visible-graph.json'
OUTPUT = REF / 'page4-t3-visible-wrapper-comparison.json'
PORTS = [
    'X2_7', 'X2_10', 'X2_11', 'X2_12', 'X2_13', 'X2_4',
    'X2_5', 'X2_6', 'X2_3', 'X3_1', 'X1_1', 'X1_2', 'X1_3',
    'X1_5', 'X1_7', 'X1_9', 'X1_12', 'X1_13', 'X1_10', 'X1_15',
]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def replace_once(text, before, after):
    if text.count(before) != 1:
        raise ValueError(f'expected one source sheet occurrence of {before!r}')
    return text.replace(before, after)


def candidate_sheet():
    sheet = SHEET.read_text()
    symbol_line = next(line for line in sheet.splitlines()
                       if line.startswith('(symbol "Monitor:Element20" '))
    pin11 = ('(pin passive line (at -10.16 2.54 0) (length 2.54) '
             '(name "11" (effects (font (size 1 1)))) '
             '(number "11" (effects (font (size 1 1)))))')
    if symbol_line.count(pin11) != 1:
        raise ValueError('19-port T3 symbol layout changed')
    pin12 = pin11.replace('2.54 0', '7.62 0').replace('"11"', '"12"')
    updated = re.sub(r'\((name|number) "(1[2-9])"',
                     lambda match: f'({match.group(1)} "{int(match.group(2)) + 1}"',
                     symbol_line)
    updated = updated.replace(pin11, pin11 + ' ' + pin12, 1)
    updated = updated.replace('Monitor:Element20', 'Monitor:Element20Page4', 1)
    updated = updated.replace('Element20_0_1', 'Element20Page4_0_1', 1)
    updated = updated.replace('Element20_1_1', 'Element20Page4_1_1', 1)
    sheet = replace_once(sheet, symbol_line, updated)
    sheet = replace_once(sheet, '(lib_id "Monitor:Element20") (at 170 498.26',
                         '(lib_id "Monitor:Element20Page4") (at 170 498.26')
    sheet = replace_once(sheet, '(property "Value" "T3_CANDIDATE" (at 170 554.06',
                         '(property "Value" "T3_PAGE4_INTERFACE" (at 170 554.06')
    for y, old, new in (
        ('500.8', 'h_hvcold', 'h_hvac'),   # X3:1 is the V21 anode pad
        ('495.72', 'h_hvac', 't3_x1_1'),  # X1:1 is a separate label
        ('485.56', 'h_upper2', 't3_x1_3'),
        ('475.4', 'h_hvcold', 't3_x1_7'),
    ):
        sheet = replace_once(sheet, f'(label "{old}" (at 135 {y} 0)',
                             f'(label "{new}" (at 135 {y} 0)')
    new_connection = (
        '\n(wire (pts (xy 135 490.64) (xy 159.84 490.64)) '
        '(stroke (width 0) (type default)) '
        '(uuid "a2c6fa96-fde0-4cea-b6fa-c4bb0ef67212"))'
        '\n(label "h_upper2" (at 135 490.64 0) '
        '(effects (font (size 1.3 1.3)) (justify left bottom)) '
        '(uuid "318300f4-106d-4c70-9306-b92c2854da52"))')
    anchor = '(wire (pts (xy 135 485.56) (xy 159.84 485.56))'
    sheet = replace_once(sheet, anchor, new_connection + '\n' + anchor)
    return sheet


def exported_pins(xml, source_id):
    root = ET.parse(xml).getroot()
    refs = [comp.get('ref') for comp in root.findall('./components/comp')
            if any(field.get('name') == 'SourceId' and field.text == source_id
                   for field in comp.findall('./fields/field'))]
    if len(refs) != 1:
        raise ValueError(f'expected one {source_id} in KiCad export')
    pins = {}
    for net in root.findall('./nets/net'):
        for node in net.findall('node'):
            if node.get('ref') == refs[0]:
                pin = node.get('pin')
                if pin in pins:
                    raise ValueError(f'duplicate {source_id} pin {pin}')
                pins[pin] = net.get('name').removeprefix('/')
    return pins


def all_exported_pins(xml):
    nodes = {}
    for net in ET.parse(xml).getroot().findall('./nets/net'):
        for node in net.findall('node'):
            key = (node.get('ref'), node.get('pin'))
            if key in nodes:
                raise ValueError(f'duplicate exported pin {key}')
            nodes[key] = net.get('name').removeprefix('/')
    return nodes


def compare(xml, original_xml, source, graph, sheet=CANDIDATE_SHEET):
    visible = {pin.replace(':', '_') for group in
               source['page4_visible_magnetic_terminals'].values() for pin in group}
    graph_order = [pin for group in graph['groups'] for pin in group['taps']]
    graph_ports = set(graph_order)
    t3 = exported_pins(xml, '012-6921:T3')
    v21 = exported_pins(xml, '012-6921:V21')
    nodes = {port: t3.get(str(index)) for index, port in enumerate(PORTS, 1)}
    original_other = {key: net for key, net in all_exported_pins(original_xml).items()
                      if key[0] != 'X1136'}
    candidate_other = {key: net for key, net in all_exported_pins(xml).items()
                       if key[0] != 'X1136'}
    checks = {
        '20_exported_pins': len(t3) == 20 and set(t3) == {str(n) for n in range(1, 21)},
        'ports_match_source_and_graph': set(PORTS) == visible == graph_ports,
        'no_unmapped_manual_16': 'X1_16' not in PORTS,
        'v21_anode_at_x3_1': nodes['X3_1'] is not None and nodes['X3_1'] == v21.get('1'),
        'v21_cathode_on_eht': v21.get('2') == 'eht' and v21['2'] != v21.get('1'),
        'x1_2_to_x2_3': nodes['X1_2'] is not None and nodes['X1_2'] == nodes['X2_3'],
        'x1_3_separate_from_x2_3': nodes['X1_3'] is not None and nodes['X1_3'] != nodes['X2_3'],
        'x2_10_to_x1_15': nodes['X2_10'] is not None and nodes['X2_10'] == nodes['X1_15'],
        'x2_11_to_x1_13': nodes['X2_11'] is not None and nodes['X2_11'] == nodes['X1_13'],
        'other_component_pins_unchanged': original_other == candidate_other,
    }
    return {
        'format': 'dac-monitor-page4-t3-visible-wrapper-comparison-v1',
        'qualification': 'source-visible external T3 interface candidate only; no qualified winding continuity, parameters or numerical stage result',
        'source_sha256': sha(SOURCE),
        'graph_sha256': sha(GRAPH),
        'historical_sheet_sha256': sha(SHEET),
        'candidate_sheet_sha256': sha(sheet),
        'generator_sha256': sha(__file__),
        'ports_in_export_order': PORTS,
        'graph_order_to_export_pin': {port: PORTS.index(port) + 1 for port in graph_order},
        'exported_nodes': nodes,
        'v21_pins': v21,
        'non_t3_exported_pin_count': len(candidate_other),
        'checks': checks,
        'passed': all(checks.values()),
        'unresolved': [
            'Manual connection 16 has no established page-4 connector-prefix mapping.',
            'X1:1, X1:3 and X1:7 are isolated in this external interface pending full conductor/return verification; the graph treats their magnetic continuity only as hypotheses.',
            'The 20-port wrapper has an opt-in connected path with provisional magnetic parameters, but no qualified magnetic parameter set or default connected selection.',
        ],
    }


def run(source_pdf):
    source = json.loads(SOURCE.read_text())
    if sha(source_pdf) != source['source']['pdf_sha256']:
        raise ValueError('page-4 PDF changed')
    graph = json.loads(GRAPH.read_text())
    if graph['source_terminal_read_sha256'] != sha(SOURCE):
        raise ValueError('page-4 graph source read changed')
    if CANDIDATE_SHEET.read_text() != candidate_sheet():
        raise ValueError('committed candidate sheet differs from generator')
    with tempfile.TemporaryDirectory() as directory:
        original_xml = Path(directory) / 'horizontal-output-original.xml'
        xml = Path(directory) / 'horizontal-output-page4.xml'
        subprocess.run(['kicad-cli', 'sch', 'export', 'netlist', '--format', 'kicadxml',
                        '-o', str(original_xml), str(SHEET)],
                       check=True, capture_output=True, text=True)
        subprocess.run(['kicad-cli', 'sch', 'export', 'netlist', '--format', 'kicadxml',
                        '-o', str(xml), str(CANDIDATE_SHEET)],
                       check=True, capture_output=True, text=True)
        return compare(xml, original_xml, source, graph, CANDIDATE_SHEET)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-pdf', type=Path,
                        default=ROOT.parents[1] / 'build/monitor/phase-a/sources/older.pdf')
    parser.add_argument('--output', type=Path, default=OUTPUT)
    parser.add_argument('--write-sheet', action='store_true',
                        help='regenerate the committed candidate sheet before checking it')
    args = parser.parse_args()
    if args.write_sheet:
        CANDIDATE_SHEET.write_text(candidate_sheet())
    result = run(args.source_pdf)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(f"{sum(result['checks'].values())}/{len(result['checks'])} source-visible wrapper checks pass")
    if not result['passed']:
        raise SystemExit(1)
