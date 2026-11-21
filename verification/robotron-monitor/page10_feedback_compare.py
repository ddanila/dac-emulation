"""Compare the page-10 A3 feedback read against a fresh KiCad netlist."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / 'reference/k7222-11/page10-feedback-source-netlist.json'
INVENTORY = ROOT / 'reference/k7222-11/inventory.json'
SHEET = ROOT / 'circuits/k7222-11-vertical-output.kicad_sch'
NAMES = {'AMP_INV': 'amp_inv', 'THRESHOLD_LOWER': 'threshold_lower',
         'THRESHOLD_UPPER': 'threshold_upper', 'Y2_RETURN': 'y2',
         'ZERO_RETURN': '0'}
PIN = {'A3:4': '2',  # Physical DIP pin 4 is model pin 2.
       'V25:A': '1', 'V25:K': '2', 'V23:A': '1', 'V23:K': '2'}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def compare(source, xml):
    if source['format'] != 'dac-monitor-page10-feedback-source-netlist-v1':
        raise ValueError('unsupported feedback source read')
    if set(source['nets']) != set(NAMES):
        raise ValueError('incomplete feedback net names')
    expected = {}
    for label, terminals in source['nets'].items():
        for terminal in terminals:
            part, pin = terminal.split(':')
            key = ('012-6931:' + part, PIN.get(terminal, pin))
            if key in expected:
                raise ValueError('duplicate source terminal: ' + terminal)
            expected[key] = NAMES[label]
    required = {('012-6931:' + part, pin) for part, pin in [
        ('A3', '2'), ('R43', '2'), ('R45', '1'), ('R45', '2'),
        ('R46', '1'), ('R46', '2'), ('R47', '1'), ('R47', '2'),
        ('R27', '1'), ('X2', '4'), ('V25', '1'), ('V25', '2'),
        ('V23', '1'), ('V23', '2'), ('R53', '2'), ('R52', '2'),
        ('R51', '1'), ('R51', '2')]}
    if set(expected) != required:
        raise ValueError('feedback read omitted a required source terminal')

    inventory = json.loads(INVENTORY.read_text())
    for part, value in source['resistor_values_ohm'].items():
        row = next(p for p in inventory['parts'] if p['id'] == '012-6931:' + part)
        if row['value'] != value or row['unit'] != 'ohm':
            raise ValueError(part + ' source read conflicts with inventory')

    root = ET.parse(xml).getroot()
    refs, values = {}, {}
    for component in root.findall('./components/comp'):
        source_id = next((p.get('value') for p in component.findall('property')
                          if p.get('name') == 'SourceId'), None)
        if source_id in source['scope']:
            if source_id in values:
                raise ValueError('duplicate KiCad SourceId: ' + source_id)
            refs[component.get('ref')] = source_id
            values[source_id] = component.findtext('value')
    actual = {}
    for net in root.findall('./nets/net'):
        for node in net.findall('node'):
            if node.get('ref') in refs:
                actual[(refs[node.get('ref')], node.get('pin'))] = net.get('name').lstrip('/')
    mismatches = [dict(source_id=part, pin=pin, expected_net=name,
                       actual_net=actual.get((part, pin)))
                  for (part, pin), name in sorted(expected.items())
                  if actual.get((part, pin)) != name]
    missing = sorted(set(source['scope']) - set(values))
    value_matches = {part: values.get('012-6931:' + part) in
                     {str(value), f'{value/1000:g}k'}
                     for part, value in source['resistor_values_ohm'].items()}
    return dict(format='dac-monitor-page10-feedback-comparison-v1',
                qualification='partial A1 check of A3 feedback, diode thresholds and Y2 return; C23 source conflict and whole page 10 remain open',
                source_netlist_sha256=sha(SOURCE),
                source_pdf_sha256=source['source']['pdf_sha256'],
                inventory_sha256=sha(INVENTORY), sheet_sha256=sha(SHEET),
                source_pins=len(expected), matched_pins=len(expected) - len(mismatches),
                missing_source_parts=missing, missing_or_changed_pins=mismatches,
                resistor_values_match=value_matches,
                source_conflicts=source['source_conflicts'],
                passed=not missing and not mismatches and all(value_matches.values()))


def run(source_pdf):
    source = json.loads(SOURCE.read_text())
    if sha(source_pdf) != source['source']['pdf_sha256']:
        raise ValueError('source PDF differs from recorded page-10 reading')
    for conflict in source['source_conflicts']:
        manual = source_pdf.with_name(conflict['operation_manual_file'])
        if sha(manual) != conflict['operation_manual_pdf_sha256']:
            raise ValueError('operating manual differs from recorded C23 reading')
    with tempfile.TemporaryDirectory() as directory:
        xml = Path(directory) / 'live.xml'
        subprocess.run(['kicad-cli', 'sch', 'export', 'netlist', '--format',
                        'kicadxml', '-o', str(xml), str(SHEET)],
                       check=True, capture_output=True, text=True)
        return compare(source, xml)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-pdf', type=Path,
                        default=ROOT.parent.parent / 'build/monitor/phase-a/sources/older.pdf')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = run(args.source_pdf)
    if args.output:
        args.output.write_text(json.dumps(result, indent=2) + '\n')
    else:
        print(json.dumps(result, indent=2))
    raise SystemExit(0 if result['passed'] else 2)
