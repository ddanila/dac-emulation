"""Close the five remaining page-9 oscillator/filter pin reads against fresh exports."""
import argparse
import hashlib
import json
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

import page9_oscillator_compare as oscillator
import page9_sync_input_compare as sync_input

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / 'reference/k7222-11/page9-oscillator-gap-source-read.json'
SHEETS = (oscillator.SHEET, sync_input.SHEET)
NET_NAMES = {'12P': 'p12', 'OSC_SUPPLY': 'vertical_supply', '00': '0',
             'VF2': 'vf2', 'VF_DIODE': 'vf_diode', 'TRIGGER': 'vertical_trigger'}
PIN_NAMES = {
    'R26': {'left': '2', 'right': '1'},
    'C16': {'positive': '1', 'negative': '2'},
    'R28': {'upper': '1', 'lower': '2'},
    'V6': {'anode': '1', 'cathode': '2'},
    'C12': {'upper': '1', 'lower': '2'},
}
UNPOLARIZED = {'R26', 'R28', 'C12'}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def exported(xml):
    root = ET.parse(xml).getroot()
    references = {}
    for comp in root.findall('./components/comp'):
        values = [p.get('value') for p in comp.findall('property')
                  if p.get('name') == 'SourceId']
        if len(values) != 1 or values[0] in references.values():
            raise ValueError('missing or duplicate exported SourceId')
        references[comp.get('ref')] = values[0]
    pins = {sid: {} for sid in references.values() if sid.startswith('012-6931:')}
    for net in root.findall('./nets/net'):
        name = net.get('name').lstrip('/')
        for node in net.findall('node'):
            sid = references[node.get('ref')]
            if sid not in pins:
                continue
            number = node.get('pin')
            if number in pins[sid]:
                raise ValueError('exported terminal occurs on two nets')
            pins[sid][number] = name
    return pins


def compare(source, oscillator_xml, sync_xml):
    if (source.get('format') != 'dac-monitor-page9-oscillator-gap-source-read-v1'
            or set(source['source_nets']) != set(NET_NAMES)):
        raise ValueError('oscillator gap source read changed')
    expected = {part: {} for part in PIN_NAMES}
    for source_net, terminals in source['source_nets'].items():
        for terminal in terminals:
            part, label = terminal.split(':')
            if part not in expected or label not in PIN_NAMES[part] or label in expected[part]:
                raise ValueError('unknown or repeated source terminal: ' + terminal)
            expected[part][label] = NET_NAMES[source_net]
    if any(set(labels) != set(PIN_NAMES[part]) for part, labels in expected.items()):
        raise ValueError('five-part source coverage changed')

    oscillator_pins = exported(oscillator_xml)
    sync_pins = exported(sync_xml)
    if set(oscillator_pins) & set(sync_pins):
        raise ValueError('source ID appears on both exported sheets')
    all_exported = oscillator_pins | sync_pins
    connector_ids = {'012-6931:X1', '012-6931:X3'}
    if not connector_ids <= set(all_exported):
        raise ValueError('oscillator/filter page-edge connectors changed')
    modeled = {sid: pins for sid, pins in all_exported.items() if sid not in connector_ids}
    mismatches = []
    for part, labels in expected.items():
        actual = modeled.get('012-6931:' + part)
        if actual is None or set(actual) != {'1', '2'}:
            mismatches.append({'part': part, 'reason': 'missing or extra exported pin'})
        elif part in UNPOLARIZED:
            if sorted(labels.values()) != sorted(actual.values()):
                mismatches.append({'part': part, 'source_nets': sorted(labels.values()),
                                   'model_nets': sorted(actual.values())})
        elif any(actual[PIN_NAMES[part][label]] != net for label, net in labels.items()):
            mismatches.append({'part': part, 'source_nets': labels, 'model_pins': actual})

    old_osc = json.loads(oscillator.SOURCE.read_text())
    old_sync = json.loads(sync_input.SOURCE.read_text())
    oscillator_result = oscillator.compare(old_osc, oscillator_xml)
    sync_result = sync_input.compare(old_sync, sync_xml)
    old_osc_terminals = [terminal for members in old_osc['nodes'].values()
                         for terminal in members]
    if len(old_osc_terminals) != len(set(old_osc_terminals)):
        raise ValueError('old oscillator source terminal repeated')
    old_osc_parts = {terminal.split('.')[0] for terminal in old_osc_terminals}
    old_sync_parts = set(old_sync['scope']['parts'])
    if old_osc_parts & old_sync_parts or set(PIN_NAMES) & (old_osc_parts | old_sync_parts):
        raise ValueError('source scopes overlap')
    source_parts = old_osc_parts | old_sync_parts | set(PIN_NAMES)
    exported_parts = {sid.split(':', 1)[1] for sid in modeled}
    if source_parts != exported_parts:
        raise ValueError('oscillator/filter source coverage differs from exported parts: '
                         f'missing={sorted(exported_parts - source_parts)}, '
                         f'extra={sorted(source_parts - exported_parts)}')
    for part in old_osc_parts:
        if sum(terminal.startswith(part + '.') for terminal in old_osc_terminals) != len(modeled['012-6931:' + part]):
            raise ValueError('old oscillator source pins incomplete: ' + part)
    source_slots = len(old_osc_terminals)
    source_slots += 2 * len(old_sync_parts)
    source_slots += sum(len(labels) for labels in expected.values())
    model_slots = sum(len(pins) for pins in modeled.values())
    if len(source_parts) != 18 or source_slots != 38 or model_slots != 38:
        raise ValueError('oscillator/filter terminal coverage changed')
    passed = not mismatches and oscillator_result['passed'] and sync_result['passed']
    return {
        'format': 'dac-monitor-page9-oscillator-gap-comparison-v1',
        'qualification': 'all modeled page-9 oscillator/filter electrical slots compared in three scoped reads; whole page and stage behavior remain open',
        'source_read_sha256': sha(SOURCE),
        'oscillator_source_read_sha256': sha(oscillator.SOURCE),
        'sync_source_read_sha256': sha(sync_input.SOURCE),
        'oscillator_sheet_sha256': sha(oscillator.SHEET),
        'sync_sheet_sha256': sha(sync_input.SHEET),
        'new_parts_checked': sorted(PIN_NAMES),
        'new_terminals_checked': sum(len(labels) for labels in expected.values()),
        'combined_parts_checked': len(source_parts),
        'combined_source_slots': source_slots,
        'combined_exported_slots': model_slots,
        'page_edge_connectors_not_counted': sorted(connector_ids),
        'previous_oscillator_groups_passed': oscillator_result['passed'],
        'previous_sync_input_passed': sync_result['passed'],
        'new_mismatches': mismatches,
        'passed': passed,
        'remaining': source['remaining'],
    }


def run(source_pdf):
    source = json.loads(SOURCE.read_text())
    if sha(source_pdf) != source['source']['pdf_sha256']:
        raise ValueError('schematic PDF differs from source read')
    for view in source['source']['views']:
        if sha(ROOT.parent.parent / view['path']) != view['sha256']:
            raise ValueError('source image differs from source read: ' + view['path'])
    with tempfile.TemporaryDirectory() as directory:
        xmls = []
        for sheet in SHEETS:
            xml = Path(directory) / (sheet.stem + '.xml')
            subprocess.run(['kicad-cli', 'sch', 'export', 'netlist', '--format',
                            'kicadxml', '-o', str(xml), str(sheet)],
                           check=True, capture_output=True, text=True)
            xmls.append(xml)
        return compare(source, *xmls)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-pdf', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = run(args.source_pdf)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(f"page-9 oscillator/filter: {result['combined_source_slots']}/{result['combined_exported_slots']} electrical slots checked; passed={result['passed']}")
    raise SystemExit(0 if result['passed'] else 2)
