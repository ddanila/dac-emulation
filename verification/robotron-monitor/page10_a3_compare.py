"""Compare a source-first read of page-10 A3 pins and compensation with KiCad."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / 'reference/k7222-11/page10-a3-source-netlist.json'
SHEET = ROOT / 'circuits/k7222-11-vertical-output.kicad_sch'
PARTS = {'A3', 'C26', 'C27', 'R54', 'R48'}
PIN_MAP = {'3': '1', '4': '2', '5': '3', '6': '4',
           '9': '5', '10': '6', '11': '7', '12': '8'}
NET_NAMES = {
    'COMP_A': 'amp_ca', 'INVERTING_INPUT': 'amp_inv',
    'NONINVERTING_INPUT': 'amp_noninv', 'NEGATIVE_SUPPLY': 'n16',
    'OUTPUT_COMPENSATION': 'amp_co', 'AMPLIFIER_OUTPUT': 'amp_out',
    'POSITIVE_SUPPLY': 'amp_vp', 'COMP_B': 'amp_cb',
    'COMP_SERIES': 'comp_series',
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def compare(source, xml):
    if source.get('format') != 'dac-monitor-page10-a3-source-netlist-v1':
        raise ValueError('unsupported source netlist')
    if (source['source']['page'] != 10
            or source['scope']['board'] != '012-6931'
            or source['scope']['parts'] != ['A3', 'C26', 'C27', 'R54', 'R48']):
        raise ValueError('wrong page-10 source scope')
    if source['physical_to_model_pins'] != PIN_MAP or set(source['nets']) != set(NET_NAMES):
        raise ValueError('source pin or net translation changed')

    expected = {}
    physical_pins = {part: set() for part in PARTS}
    for source_net, terminals in source['nets'].items():
        for terminal in terminals:
            part, physical_pin = terminal.split(':')
            if part not in PARTS:
                raise ValueError('unexpected source part: ' + part)
            if part == 'A3':
                if physical_pin not in PIN_MAP:
                    raise ValueError('unexpected A3 physical pin: ' + physical_pin)
                model_pin = PIN_MAP[physical_pin]
            else:
                if physical_pin not in {'1', '2'}:
                    raise ValueError('unexpected passive pin: ' + terminal)
                model_pin = physical_pin
            key = ('012-6931:' + part, model_pin)
            if key in expected:
                raise ValueError('duplicate source terminal: ' + terminal)
            expected[key] = NET_NAMES[source_net]
            physical_pins[part].add(physical_pin)
    if physical_pins['A3'] != set(PIN_MAP):
        raise ValueError('A3 source read lacks an active physical pin')
    for part in ('C26', 'C27', 'R54'):
        if physical_pins[part] != {'1', '2'}:
            raise ValueError('compensation component source read is incomplete: ' + part)
    if physical_pins['R48'] != {'1'}:
        raise ValueError('source read should cover only R48 amplifier end')

    root = ET.parse(xml).getroot()
    refs = {}
    for comp in root.findall('./components/comp'):
        source_id = next((prop.get('value') for prop in comp.findall('property')
                          if prop.get('name') == 'SourceId'), None)
        if source_id in {'012-6931:' + part for part in PARTS}:
            if source_id in refs.values():
                raise ValueError('duplicate KiCad SourceId: ' + source_id)
            refs[comp.get('ref')] = source_id
    if set(refs.values()) != {'012-6931:' + part for part in PARTS}:
        raise ValueError('A3 or compensation part missing from KiCad export')
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
    extras = [dict(source_id=part, pin=pin, actual_net=net)
              for (part, pin), net in sorted(actual.items())
              if (part, pin) not in expected and (part, pin) != ('012-6931:R48', '2')]
    return dict(format='dac-monitor-page10-a3-comparison-v1',
                qualification='partial A1 comparison of A3 physical pin functions and compensation; P09A electrical identity and whole page 10 remain open',
                source_netlist_sha256=sha(SOURCE),
                source_pdf_sha256=source['source']['pdf_sha256'],
                sheet_sha256=sha(SHEET), source_pins=len(expected),
                matched_pins=len(expected) - len(mismatches),
                physical_to_model_pins=PIN_MAP,
                missing_or_changed_pins=mismatches,
                extra_kicad_pins=extras,
                passed=not mismatches and not extras)


def run():
    source = json.loads(SOURCE.read_text())
    with tempfile.TemporaryDirectory() as directory:
        xml = Path(directory) / 'vertical-output.xml'
        subprocess.run(['kicad-cli', 'sch', 'export', 'netlist', '--format',
                        'kicadxml', '-o', str(xml), str(SHEET)],
                       check=True, capture_output=True, text=True)
        return compare(source, xml)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = run()
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(f"{result['matched_pins']}/{result['source_pins']} source pins match")
    return 0 if result['passed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
