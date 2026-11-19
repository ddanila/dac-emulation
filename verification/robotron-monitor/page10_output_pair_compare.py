"""Check the source-read page-10 vertical output pair against a fresh KiCad export."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / 'reference/k7222-11/page10-output-pair-source-netlist.json'
SHEET = ROOT / 'circuits/k7222-11-vertical-output.kicad_sch'
NET_NAMES = {
    'UPPER_RAIL': 'p22', 'UPPER_DRIVER': 'upper_emitter',
    'Y1_OUTPUT': 'y1', 'LOWER_DRIVER': 'lower_emitter',
    'LOWER_RAIL': 'n16',
}
PIN_NUMBERS = {'C': '1', 'B': '2', 'E': '3'}
MODEL_POLARITY = {'VERT_POWER_N': 'NPN', 'VERT_POWER_P': 'PNP'}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def compare(source, xml):
    if source.get('format') != 'dac-monitor-page10-output-pair-source-netlist-v1':
        raise ValueError('unsupported source netlist')
    if source['source']['page'] != 10 or source['scope']['board'] != '012-6931':
        raise ValueError('wrong source page or board')
    if source['scope']['parts'] != ['V18', 'V26', 'V27', 'V28']:
        raise ValueError('unexpected output-pair source scope')
    if set(source['nets']) != set(NET_NAMES):
        raise ValueError('source nets lack explicit KiCad translations')
    expected = {}
    for source_net, terminals in source['nets'].items():
        for terminal in terminals:
            part, pin = terminal.split(':')
            if part not in source['scope']['parts'] or pin not in PIN_NUMBERS:
                raise ValueError('invalid source terminal: ' + terminal)
            key = ('012-6931:' + part, PIN_NUMBERS[pin])
            if key in expected:
                raise ValueError('duplicate source terminal: ' + terminal)
            expected[key] = NET_NAMES[source_net]
    for part in ('V27', 'V28'):
        if {pin for source_id, pin in expected if source_id == '012-6931:' + part} != {'1', '2', '3'}:
            raise ValueError('output transistor has an incomplete source read: ' + part)
    if source['printed_polarity'] != {'V27': 'NPN', 'V28': 'PNP'}:
        raise ValueError('source polarity must be re-reviewed')

    root = ET.parse(xml).getroot()
    refs, values = {}, {}
    for comp in root.findall('./components/comp'):
        source_id = next((prop.get('value') for prop in comp.findall('property')
                          if prop.get('name') == 'SourceId'), None)
        if source_id in {'012-6931:' + part for part in source['scope']['parts']}:
            if source_id in refs.values():
                raise ValueError('duplicate KiCad SourceId: ' + source_id)
            refs[comp.get('ref')] = source_id
            values[source_id] = comp.findtext('value')
    if set(values) != {'012-6931:' + part for part in source['scope']['parts']}:
        raise ValueError('output pair or driver is missing from KiCad export')
    actual = {}
    for net in root.findall('./nets/net'):
        for node in net.findall('node'):
            if node.get('ref') in refs:
                key = (refs[node.get('ref')], node.get('pin'))
                if key in actual:
                    raise ValueError('KiCad terminal occurs on two nets')
                actual[key] = net.get('name').lstrip('/')
    mismatches = [dict(source_id=part, pin=pin, expected_net=net,
                       actual_net=actual.get((part, pin)))
                  for (part, pin), net in sorted(expected.items())
                  if actual.get((part, pin)) != net]
    polarity = {part: MODEL_POLARITY.get(values['012-6931:' + part])
                for part in source['printed_polarity']}
    return dict(format='dac-monitor-page10-output-pair-comparison-v1',
                qualification='partial A1 check of ten output-pair and driver terminals; whole page 10 remains open',
                source_netlist_sha256=sha(SOURCE),
                source_pdf_sha256=source['source']['pdf_sha256'],
                sheet_sha256=sha(SHEET),
                source_pins=len(expected), matched_pins=len(expected) - len(mismatches),
                output_transistor_pins_checked=6,
                printed_polarity=source['printed_polarity'], model_polarity=polarity,
                missing_or_changed_pins=mismatches,
                passed=not mismatches and polarity == source['printed_polarity'])


def run(source_pdf):
    source = json.loads(SOURCE.read_text())
    if sha(source_pdf) != source['source']['pdf_sha256']:
        raise ValueError('source PDF differs from recorded page-10 reading')
    with tempfile.TemporaryDirectory() as directory:
        xml = Path(directory) / 'vertical-output.xml'
        subprocess.run(['kicad-cli', 'sch', 'export', 'netlist', '--format',
                        'kicadxml', '-o', str(xml), str(SHEET)],
                       check=True, capture_output=True, text=True)
        return compare(source, xml)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-pdf', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = run(args.source_pdf)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(f"{result['matched_pins']}/{result['source_pins']} source pins match")
    return 0 if result['passed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
