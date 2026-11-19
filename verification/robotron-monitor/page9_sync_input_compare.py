"""Compare the independently read page-9 sync input with a fresh KiCad export.

The four parts are unpolarized passives; the source scan does not number their
leads. Compare each component's two endpoint nets without assigning a false
physical pin orientation to the drawing.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT/'reference/k7222-11/page9-sync-input-source-netlist.json'
SHEET = ROOT/'circuits/k7222-11-sync-filter.kicad_sch'
NET_NAMES = {'SYNC_IN': 'sync_gate', 'TP2': 'vf1',
             'INTEGRATOR_2': 'vf2', '0': '0'}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def compare(source, xml):
    if source.get('format') != 'dac-monitor-independent-source-netlist-v1':
        raise ValueError('unsupported source netlist')
    if source['source']['page'] != 9 or source['scope']['board'] != '012-6931':
        raise ValueError('wrong source page or board')
    if set(source['nets']) != set(NET_NAMES):
        raise ValueError('source net has no explicit KiCad translation')
    parts = {'012-6931:'+part for part in source['scope']['parts']}
    expected = {part: [] for part in parts}
    labels = set()
    for source_net, terminals in source['nets'].items():
        for terminal in terminals:
            part, label = terminal.rsplit(':', 1)
            source_id = '012-6931:'+part
            if source_id not in parts or terminal in labels or label not in ('L', 'R', 'T', 'B'):
                raise ValueError('invalid or duplicate source terminal: '+terminal)
            labels.add(terminal)
            expected[source_id].append(NET_NAMES[source_net])
    if any(len(nets) != 2 or len(set(nets)) != 2 for nets in expected.values()):
        raise ValueError('each scoped passive must have two distinct endpoint nets')

    root = ET.parse(xml).getroot()
    refs = {}
    seen_source_ids = set()
    for comp in root.findall('./components/comp'):
        source_id = next((field.get('value') for field in comp.findall('property')
                          if field.get('name') == 'SourceId'), None)
        if source_id is None or source_id in seen_source_ids:
            raise ValueError('missing or duplicate KiCad SourceId')
        refs[comp.get('ref')] = source_id
        seen_source_ids.add(source_id)
    actual = {part: {} for part in parts}
    for net in root.findall('./nets/net'):
        name = net.get('name').lstrip('/')
        for node in net.findall('node'):
            part = refs[node.get('ref')]
            if part not in parts:
                continue
            pin = node.get('pin')
            if pin in actual[part]:
                raise ValueError('KiCad terminal occurs on two nets')
            actual[part][pin] = name
    missing_or_changed = [
        dict(source_id=part, expected_endpoint_nets=sorted(nets),
             actual_endpoint_nets=sorted(actual[part].values()),
             actual_pins=actual[part])
        for part, nets in sorted(expected.items())
        if sorted(nets) != sorted(actual[part].values())
        or set(actual[part]) != {'1', '2'}
    ]
    return dict(format='dac-monitor-page9-sync-input-comparison-v1',
                qualification='partial A1 source-to-KiCad endpoint comparison; unpolarized leads unordered and whole page 9 open',
                source_netlist_sha256=sha(SOURCE),
                source_pdf_sha256=source['source']['pdf_sha256'],
                sheet_sha256=sha(SHEET),
                source_parts=len(parts), source_endpoints=len(labels),
                matched_parts=len(parts)-len(missing_or_changed),
                matched_endpoints=2*(len(parts)-len(missing_or_changed)),
                missing_or_changed_parts=missing_or_changed,
                passed=not missing_or_changed)


def run(source_pdf):
    source = json.loads(SOURCE.read_text())
    if sha(source_pdf) != source['source']['pdf_sha256']:
        raise ValueError('source PDF differs from recorded independent reading')
    with tempfile.TemporaryDirectory() as directory:
        xml = Path(directory)/'sync-filter.xml'
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
    print(f"{result['matched_endpoints']}/{result['source_endpoints']} "
          'source endpoints match')
    return 0 if result['passed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
