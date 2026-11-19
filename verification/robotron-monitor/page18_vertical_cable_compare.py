"""Compare the page-18 X4-to-X3 cable with fresh physical KiCad connector pins."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import xml.etree.ElementTree as ET

from page18_frame_compare import SIGNAL_NETS

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT/'reference/k7222-11/page18-interconnect-transcription.json'
SHEETS = {
    '012-6921:X4': ROOT/'circuits/k7222-11-input.kicad_sch',
    '012-6931:X3': ROOT/'circuits/k7222-11-sync-filter.kicad_sch',
}
CABLE = '1.11.017308.0'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def physical_pins(xml, source_id):
    root = ET.parse(xml).getroot()
    matches = []
    for comp in root.findall('./components/comp'):
        fields = {field.get('name'): field.text for field in comp.findall('./fields/field')}
        if fields.get('SourceId') == source_id:
            if fields.get('AuditOnly') != 'source-connector':
                raise ValueError('physical connector is not audit-only')
            matches.append(comp.get('ref'))
    if len(matches) != 1:
        raise ValueError('missing or duplicate physical connector: '+source_id)
    pins = {}
    for net in root.findall('./nets/net'):
        for node in net.findall('node'):
            if node.get('ref') == matches[0]:
                pin = node.get('pin')
                if pin in pins:
                    raise ValueError('physical connector pin occurs twice')
                pins[pin] = net.get('name').removeprefix('/')
    return pins


def compare(source, exports, *, pdf_sha256):
    if source.get('format') != 'dac-monitor-interconnect-source-v1':
        raise ValueError('unsupported source transcription')
    if source['source']['page'] != 18 or source['source']['pdf_sha256'] != pdf_sha256:
        raise ValueError('wrong scanned schematic source')
    cables = [c for c in source['cables'] if c['part'] == CABLE]
    if len(cables) != 1 or (cables[0]['from'], cables[0]['to']) != tuple(SHEETS):
        raise ValueError('page-18 vertical cable is missing or changed')
    cable = cables[0]
    expected_pairs = [[str(pin), str(pin)] for pin in range(1, 7)]
    if cable['pin_pairs'] != expected_pairs:
        raise ValueError('page-18 vertical cable pin pairing is incomplete')
    actual = {connector: physical_pins(exports[connector], connector) for connector in SHEETS}
    expected = {}
    for connector in SHEETS:
        labels = source['connectors'][connector]
        if set(labels) != {str(pin) for pin in range(1, 7)}:
            raise ValueError('page-18 connector source pin list is incomplete')
        expected[connector] = {pin: SIGNAL_NETS[label] for pin, label in labels.items()}
    rows = []
    for from_pin, to_pin in cable['pin_pairs']:
        left, right = cable['from'], cable['to']
        if source['connectors'][left][from_pin] != source['connectors'][right][to_pin]:
            raise ValueError('source cable signals disagree')
        net = expected[left][from_pin]
        rows.append(dict(from_pin=from_pin, to_pin=to_pin,
                         source_signal=source['connectors'][left][from_pin],
                         expected_model_net=net,
                         main_board_net=actual[left].get(from_pin),
                         vertical_board_net=actual[right].get(to_pin)))
    extra = {connector: sorted(set(actual[connector])-set(expected[connector]))
             for connector in SHEETS}
    passed = all(row['main_board_net'] == row['expected_model_net']
                 and row['vertical_board_net'] == row['expected_model_net'] for row in rows)
    return dict(format='dac-monitor-page18-vertical-cable-comparison-v1',
                qualification='one six-wire cable compared pin-to-pin; other page-18 paths remain open',
                source_sha256=sha(SOURCE), source_pdf_sha256=pdf_sha256,
                sheet_sha256={connector: sha(sheet) for connector, sheet in SHEETS.items()},
                cable_part=CABLE, connector_pins_checked=12, cable_pairs_checked=6,
                pin_pairs=rows, extra_kicad_pins=extra,
                passed=passed and not any(extra.values()))


def run(source_pdf):
    source = json.loads(SOURCE.read_text())
    if sha(source_pdf) != source['source']['pdf_sha256']:
        raise ValueError('source PDF differs from independent reading')
    with tempfile.TemporaryDirectory() as directory:
        exports = {}
        for connector, sheet in SHEETS.items():
            xml = Path(directory)/(connector.replace(':', '-')+'.xml')
            subprocess.run(['kicad-cli', 'sch', 'export', 'netlist', '--format', 'kicadxml',
                            '-o', str(xml), str(sheet)], check=True, capture_output=True, text=True)
            exports[connector] = xml
        return compare(source, exports, pdf_sha256=sha(source_pdf))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-pdf', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = run(args.source_pdf)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2)+'\n')
    print(f"{sum(row['main_board_net'] == row['expected_model_net'] and row['vertical_board_net'] == row['expected_model_net'] for row in report['pin_pairs'])}/6 cable pairs match")
    return 0 if report['passed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
