"""Compare the page-4 T3 X2:4/C31/C32 branch with a fresh KiCad export."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / 'reference/k7222-11/page4-t3-x2-return-source-netlist.json'
TRANSCRIPTION = ROOT / 'reference/k7222-11/horizontal-output-transcription.json'
SHEET = ROOT / 'circuits/k7222-11-horizontal-output.kicad_sch'
IDS = {f'012-6921:{name}' for name in ('T3', 'C31', 'C32', 'X5')}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def pins_by_source_id(xml):
    root = ET.parse(xml).getroot()
    refs = {}
    for comp in root.findall('./components/comp'):
        source_id = next((field.text for field in comp.findall('./fields/field')
                          if field.get('name') == 'SourceId'), None)
        if source_id in IDS:
            if source_id in refs.values():
                raise ValueError('duplicate scoped page-4 part')
            refs[comp.get('ref')] = source_id
    if set(refs.values()) != IDS:
        raise ValueError('scoped page-4 part missing')
    pins = {source_id: {} for source_id in IDS}
    for net in root.findall('./nets/net'):
        for node in net.findall('node'):
            source_id = refs.get(node.get('ref'))
            if source_id:
                pin = node.get('pin')
                if pin in pins[source_id]:
                    raise ValueError('scoped page-4 pin occurs twice')
                pins[source_id][pin] = net.get('name').removeprefix('/')
    return pins


def compare(source, transcription, xml):
    if source['format'] != 'dac-monitor-page4-t3-x2-return-source-netlist-v1':
        raise ValueError('wrong X2:4 source read')
    expected = {
        'X2_4_RETURN': {'T3:X2:4', 'C31:one_plate', 'C32:one_plate'},
        'H2_EXTERNAL_RETURN': {'C31:other_plate', 'C32:other_plate', 'X5:5'},
    }
    if {name: set(parts) for name, parts in source['scope']['nets'].items()} != expected:
        raise ValueError('source X2:4 branch changed')
    pins = pins_by_source_id(xml)
    ports = transcription['ports']
    if len(set(ports)) != len(ports) or 'X2_4' not in ports:
        raise ValueError('T3 port list changed')
    t3_pin = str(ports.index('X2_4') + 1)
    t3_net = pins['012-6921:T3'].get(t3_pin)
    c31 = pins['012-6921:C31']
    c32 = pins['012-6921:C32']
    c31_other = next((net for net in c31.values() if net != t3_net), None)
    c32_other = next((net for net in c32.values() if net != t3_net), None)
    checks = {
        't3_x2_4_present': t3_net is not None,
        'c31_two_distinct_terminals': set(c31) == {'1', '2'} and len(set(c31.values())) == 2,
        'c32_two_distinct_terminals': set(c32) == {'1', '2'} and len(set(c32.values())) == 2,
        'c31_one_plate_at_x2_4': t3_net in c31.values(),
        'c32_one_plate_at_x2_4': t3_net in c32.values(),
        'other_plates_join': c31_other is not None and c31_other == c32_other,
        'h2_reaches_x5_pin5': c31_other is not None and c31_other == pins['012-6921:X5'].get('5'),
        'h2_crosses_ground_without_junction': c31_other not in (None, '0'),
        'return_distinct_from_collector': t3_net != pins['012-6921:T3'].get(
            str(ports.index('X2_7') + 1)),
    }
    return dict(
        format='dac-monitor-page4-t3-x2-return-comparison-v1',
        qualification='scoped X2:4 capacitor return to H2/X5:5; no full page-4 netlist, T3 internal graph or source-bounded return waveform',
        source_sha256=sha(SOURCE),
        source_pdf_sha256=source['source']['pdf_sha256'],
        transcription_sha256=sha(TRANSCRIPTION),
        sheet_sha256=sha(SHEET),
        model_nets=dict(x2_4=t3_net, c31=c31, c32=c32,
                        common_other_plate=c31_other, x5_pin5=pins['012-6921:X5'].get('5')),
        checks=checks,
        unresolved=source['unresolved'],
        passed=all(checks.values()))


def run(source_pdf, source_crop, h2_crop):
    source = json.loads(SOURCE.read_text())
    if (sha(source_pdf) != source['source']['pdf_sha256'] or
            sha(source_crop) != source['source']['views'][2]['sha256'] or
            sha(h2_crop) != source['source']['views'][4]['sha256']):
        raise ValueError('source PDF or X2:4/H2 crop changed')
    transcription = json.loads(TRANSCRIPTION.read_text())
    with tempfile.TemporaryDirectory() as directory:
        xml = Path(directory) / 'horizontal-output.xml'
        subprocess.run(['kicad-cli', 'sch', 'export', 'netlist', '--format',
                        'kicadxml', '-o', str(xml), str(SHEET)],
                       check=True, capture_output=True, text=True)
        return compare(source, transcription, xml)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-pdf', type=Path, required=True)
    parser.add_argument('--source-crop', type=Path, required=True)
    parser.add_argument('--h2-crop', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = run(args.source_pdf, args.source_crop, args.h2_crop)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(f"{sum(report['checks'].values())}/{len(report['checks'])} X2:4 branch checks pass")
    raise SystemExit(0 if report['passed'] else 2)
