"""Check source-read page-10 vertical driver, output and Y2 return against KiCad."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / 'reference/k7222-11/page10-output-pair-source-netlist.json'
SHEET = ROOT / 'circuits/k7222-11-vertical-output.kicad_sch'
MODELS = ROOT / 'circuits/k7222-11-vertical-output-models.cir'
NET_NAMES = {
    'UPPER_RAIL': 'p22', 'UPPER_BASE': 'upper_base',
    'DIODE_19_20': 'bias_diode', 'MID_BIAS': 'bias_middle',
    'AMP_OUTPUT': 'amp_out', 'UPPER_DRIVER': 'upper_emitter',
    'Y1_OUTPUT': 'y1', 'Y2_RETURN': 'y2', 'ZERO_RETURN': '0',
    'LOWER_DRIVER': 'lower_emitter', 'LOWER_BASE': 'lower_base',
    'LOWER_RAIL': 'n16',
}
PIN_NUMBERS = {'C': '1', 'B': '2', 'E': '3',
               'A': '1', 'K': '2', '1': '1', '2': '2', '3': '3', '4': '4'}
PARTS = ['V18', 'V19', 'V20', 'V21', 'V26', 'V27', 'V28',
         'R27', 'R29', 'R36', 'R38', 'R48', 'R56', 'R61', 'X2']


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def compare(source, xml):
    if source.get('format') != 'dac-monitor-page10-output-pair-source-netlist-v4':
        raise ValueError('unsupported source netlist')
    if source['source']['page'] != 10 or source['scope']['board'] != '012-6931':
        raise ValueError('wrong source page or board')
    if source['scope']['parts'] != PARTS:
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
    for part in PARTS:
        pins = {pin for source_id, pin in expected if source_id == '012-6931:' + part}
        required = ({'3', '4'} if part == 'X2' else
                    {'1', '2'} if part in {'V19', 'V20', 'V21', 'R27', 'R29',
                                         'R36', 'R38', 'R48', 'R56', 'R61'}
                    else {'1', '2', '3'})
        if pins != required:
            raise ValueError('part has an incomplete source read: ' + part)
    if [row['part'] for row in source['diode_directions']] != ['V19', 'V20', 'V21']:
        raise ValueError('source diode direction list is incomplete')
    for row in source['diode_directions']:
        part = '012-6931:' + row['part']
        if (expected[(part, '1')] != NET_NAMES[row['anode_net']]
                or expected[(part, '2')] != NET_NAMES[row['cathode_net']]):
            raise ValueError('source diode direction conflicts with netlist')
    if source['printed_polarity'] != {'V27': 'NPN', 'V28': 'PNP'}:
        raise ValueError('source polarity must be re-reviewed')

    root = ET.parse(xml).getroot()
    refs, values = {}, {}
    for comp in root.findall('./components/comp'):
        source_id = next((prop.get('value') for prop in comp.findall('property')
                          if prop.get('name') == 'SourceId'), None)
        if source_id in {'012-6931:' + part for part in PARTS}:
            if source_id in refs.values():
                raise ValueError('duplicate KiCad SourceId: ' + source_id)
            if source_id == '012-6931:X2' and not any(
                    prop.get('name') == 'AuditOnly' and prop.get('value') == 'source-connector'
                    for prop in comp.findall('property')):
                raise ValueError('X2 is not a physical source connector')
            refs[comp.get('ref')] = source_id
            values[source_id] = comp.findtext('value')
    if set(values) != {'012-6931:' + part for part in PARTS}:
        raise ValueError('driver, diode or output part is missing from KiCad export')
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
    unscoped_connector_pins = [pin for (part, pin) in actual
                               if part == '012-6931:X2' and pin not in {'3', '4'}]
    if set(unscoped_connector_pins) != {'1', '2', '5', '6'}:
        raise ValueError('X2 physical connector is not six-pin complete')
    extras = [dict(source_id=part, pin=pin, actual_net=net)
              for (part, pin), net in sorted(actual.items()) if (part, pin) not in expected
              and not (part == '012-6931:X2' and pin in unscoped_connector_pins)]
    model_text = MODELS.read_text()
    polarity = {}
    for part in source['printed_polarity']:
        alias = values['012-6931:' + part]
        match = re.search(r'^\.model\s+' + re.escape(alias) + r'\s+(NPN|PNP)\b',
                          model_text, flags=re.I | re.M)
        polarity[part] = match.group(1).upper() if match else None
    return dict(format='dac-monitor-page10-output-pair-comparison-v4',
                qualification='partial A1 check of 34 driver, bias, output, resistor and Y2-sense terminals; whole page 10 remains open',
                source_netlist_sha256=sha(SOURCE),
                source_pdf_sha256=source['source']['pdf_sha256'],
                sheet_sha256=sha(SHEET), model_sha256=sha(MODELS),
                source_pins=len(expected), matched_pins=len(expected) - len(mismatches),
                output_transistor_pins_checked=6,
                diode_directions_checked=len(source['diode_directions']),
                yoke_and_sense_pins_checked=6,
                printed_polarity=source['printed_polarity'], model_polarity=polarity,
                missing_or_changed_pins=mismatches, extra_kicad_pins=extras,
                unscoped_x2_pins=sorted(unscoped_connector_pins),
                passed=not mismatches and not extras and polarity == source['printed_polarity'])


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
