"""Check the locally source-read V5/V11 oscillator against a fresh KiCad export."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT/'reference/k7222-11/page9-oscillator-source-read.json'
SHEET = ROOT/'circuits/k7222-11-vertical-oscillator.kicad_sch'
PINS = {'C': '1', 'B': '2', 'E': '3'}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def compare(source, xml):
    if source['format'] != 'dac-monitor-page9-oscillator-source-read-v1':
        raise ValueError('unrecognized source read')
    root = ET.parse(xml).getroot()
    refs = {}
    for comp in root.findall('./components/comp'):
        ids = [p.get('value') for p in comp.findall('property')
               if p.get('name') == 'SourceId']
        if len(ids) != 1:
            raise ValueError('missing SourceId')
        refs[comp.get('ref')] = ids[0]
    terminals = {}
    for net in root.findall('./nets/net'):
        for pin in net.findall('node'):
            part = refs[pin.get('ref')]
            if part.startswith('012-6931:'):
                key = part.split(':')[1]+'.'+pin.get('pin')
                if key in terminals:
                    raise ValueError('terminal repeated in exported nets')
                terminals[key] = net.get('name').lstrip('/')
    groups = {}
    for name, members in source['nodes'].items():
        keys = [part+'.'+PINS.get(pin, pin) for part, pin in
                (member.split('.') for member in members)]
        groups[name] = {key: terminals.get(key) for key in keys}
    checks = {name: len(set(values.values())) == 1 and None not in values.values()
              for name, values in groups.items()}
    checks['nodes_distinct'] = len({next(iter(group.values())) for group in groups.values()}) == len(groups)
    return dict(format='dac-monitor-page9-oscillator-comparison-v1',
                qualification='local V5/V11 oscillator terminal groups only; not independent whole-page review or functional validation',
                source_pdf_sha256=source['source_pdf_sha256'],
                source_read_sha256=sha(SOURCE), sheet_sha256=sha(SHEET),
                exported_groups=groups, checks=checks, passed=all(checks.values()))


def run(source_pdf):
    source = json.loads(SOURCE.read_text())
    if sha(source_pdf) != source['source_pdf_sha256']:
        raise ValueError('source PDF differs from recorded read')
    with tempfile.TemporaryDirectory() as tmp:
        xml = Path(tmp)/'oscillator.xml'
        subprocess.run(['kicad-cli', 'sch', 'export', 'netlist', '--format',
                        'kicadxml', '-o', str(xml), str(SHEET)],
                       check=True, capture_output=True, text=True)
        return compare(source, xml)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-pdf', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = run(args.source_pdf)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2)+'\n')
    print('page-9 oscillator:', 'match' if result['passed'] else 'mismatch')
    raise SystemExit(0 if result['passed'] else 2)
