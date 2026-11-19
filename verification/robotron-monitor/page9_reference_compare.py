"""Compare the independently read page-9 5 V branch with a fresh KiCad export."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT/'reference/k7222-11/page9-reference-source-netlist.json'
SHEET = ROOT/'circuits/k7222-11-regulator5.kicad_sch'
NET_NAMES = {
    '12P_FUSED': 'p12', 'R10_TO_R9': 'reg5_top',
    'ZENER_REF': 'reg5_zener', 'BASE_REF': 'reg5_base',
    'V4_COLLECTOR': 'reg5_collector', 'REF_OUTPUT': 'p5', '0': '0',
}
PIN_NUMBERS = {'A': '1', 'K': '2', 'C': '1', 'B': '2', 'E': '3',
               '+': '1', '-': '2', '1': '1', '2': '2', '3': '3'}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def compare(source, xml):
    if source.get('format') != 'dac-monitor-independent-source-netlist-v1':
        raise ValueError('unsupported source netlist')
    if source['source']['page'] != 9 or source['scope']['board'] != '012-6931':
        raise ValueError('wrong source page or board')
    if set(source['nets']) != set(NET_NAMES):
        raise ValueError('source net name has no explicit KiCad translation')
    expected = {}
    for source_net, terminals in source['nets'].items():
        for terminal in terminals:
            part, pin = terminal.rsplit(':', 1)
            key = ('012-6931:'+part, PIN_NUMBERS[pin])
            if key in expected:
                raise ValueError('duplicate source terminal: '+terminal)
            expected[key] = NET_NAMES[source_net]
    if {part.split(':', 1)[1] for part, _ in expected} != set(source['scope']['parts']):
        raise ValueError('source parts differ from declared scope')
    for diode in source['diode_directions']:
        part = '012-6931:'+diode['part']
        if (expected[(part, '1')] != NET_NAMES[diode['anode_net']]
                or expected[(part, '2')] != NET_NAMES[diode['cathode_net']]):
            raise ValueError('source zener direction conflicts with netlist')
    transistor = source['transistor'];part = '012-6931:'+transistor['part']
    for pin, field in (('1', 'collector_net'), ('2', 'base_net'), ('3', 'emitter_net')):
        if expected[(part, pin)] != NET_NAMES[transistor[field]]:
            raise ValueError('source transistor pin conflicts with netlist')
    for cap in source['capacitor_polarity']:
        part = '012-6931:'+cap['part']
        if (expected[(part, '1')] != NET_NAMES[cap['positive_net']]
                or expected[(part, '2')] != NET_NAMES[cap['negative_net']]):
            raise ValueError('source capacitor polarity conflicts with netlist')

    root = ET.parse(xml).getroot()
    refs = {}
    for comp in root.findall('./components/comp'):
        source_id = next((field.get('value') for field in comp.findall('property')
                          if field.get('name') == 'SourceId'), None)
        if source_id is None or source_id in refs.values():
            raise ValueError('missing or duplicate KiCad SourceId')
        refs[comp.get('ref')] = source_id
    actual = {}
    for net in root.findall('./nets/net'):
        name = net.get('name').lstrip('/')
        for node in net.findall('node'):
            key = (refs[node.get('ref')], node.get('pin'))
            if key in actual:
                raise ValueError('KiCad terminal occurs on two nets')
            actual[key] = name
    missing_or_changed = [dict(source_id=part, pin=pin, expected_net=net,
                               actual_net=actual.get((part, pin)))
                          for (part, pin), net in sorted(expected.items())
                          if actual.get((part, pin)) != net]
    extra = [dict(source_id=part, pin=pin, actual_net=net)
             for (part, pin), net in sorted(actual.items()) if (part, pin) not in expected]
    return dict(format='dac-monitor-page9-reference-comparison-v1',
                qualification='partial A1 source-to-KiCad pin comparison; whole page 9 remains open',
                source_netlist_sha256=sha(SOURCE),
                source_pdf_sha256=source['source']['pdf_sha256'],
                sheet_sha256=sha(SHEET),
                source_parts=len(source['scope']['parts']),
                source_pins=len(expected), matched_pins=len(expected)-len(missing_or_changed),
                zener_directions_checked=len(source['diode_directions']),
                capacitor_polarities_checked=len(source['capacitor_polarity']),
                transistor_pins_checked=3,
                missing_or_changed_pins=missing_or_changed,
                extra_kicad_pins=extra,
                passed=not missing_or_changed and not extra)


def run(source_pdf):
    source = json.loads(SOURCE.read_text())
    if sha(source_pdf) != source['source']['pdf_sha256']:
        raise ValueError('source PDF differs from recorded independent reading')
    with tempfile.TemporaryDirectory() as directory:
        xml = Path(directory)/'regulator5.xml'
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
    args.output.write_text(json.dumps(result, indent=2)+'\n')
    print(f"{result['matched_pins']}/{result['source_pins']} source pins match")
    return 0 if result['passed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
