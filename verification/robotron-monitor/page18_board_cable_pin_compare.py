"""Compare every labelled page-18 board cable pin with fresh KiCad exports."""
import argparse
import hashlib
import json
from pathlib import Path
import tempfile

import page18_frame_compare as semantic
from page18_vertical_cable_compare import physical_pins
import steady_supply

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT/'reference/k7222-11/page18-interconnect-transcription.json'
ASSEMBLY = ROOT/'reference/k7222-11/assembly.json'
SHEETS = {
    '012-6921:X5': 'k7222-11-horizontal-output',
    '012-6921:X4': 'k7222-11-input',
    '012-6921:X6': 'k7222-11-input',
    '012-6921:X3': 'k7222-11-input',
    '012-6931:X1': 'k7222-11-sync-filter',
    '012-6931:X3': 'k7222-11-sync-filter',
    '012-6891:X1': 'k7222-11-neck',
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def compare(source, assembly, exports, components, *, pdf_sha256):
    if source.get('format') != 'dac-monitor-interconnect-source-v1':
        raise ValueError('unsupported page-18 source transcription')
    if source['source']['page'] != 18 or source['source']['pdf_sha256'] != pdf_sha256:
        raise ValueError('wrong scanned page-18 source')
    semantic_report = semantic.compare(source, assembly, components)
    actual = {connector: physical_pins(exports[connector], connector) for connector in SHEETS}
    expected = {
        connector: {pin: semantic.SIGNAL_NETS[label] for pin, label in source['connectors'][connector].items()}
        for connector in SHEETS
    }
    neck = assembly['neck_connectors']['X1']
    if set(neck) - set(expected['012-6891:X1']) != {'4'} or neck['4'] != '0':
        raise ValueError('unlabelled neck X1:4 is not accounted for by page 16')
    expected['012-6891:X1']['4'] = neck['4']
    pin_misses = [
        dict(connector=connector, pin=pin, expected_net=net,
             actual_net=actual[connector].get(pin))
        for connector, pins in expected.items()
        for pin, net in pins.items()
        if actual[connector].get(pin) != net
    ]
    extras = [
        dict(connector=connector, pin=pin, actual_net=net)
        for connector, pins in actual.items()
        for pin, net in pins.items()
        if pin not in expected[connector]
    ]
    cable_rows = []
    semantic_rows = {(row['cable'], row['from_pin'], row['to_pin']): row
                     for row in semantic_report['cable_pairs']}
    for cable in source['cables']:
        if cable['part'] not in semantic.FRAME_CABLES:
            continue
        left, right = cable['from'], cable['to']
        if left not in SHEETS or right not in SHEETS:
            raise ValueError('frame cable has an unexported board endpoint')
        for from_pin, to_pin in cable['pin_pairs']:
            left_label = source['connectors'][left][from_pin]
            right_label = source['connectors'][right][to_pin]
            if left_label != right_label:
                raise ValueError('source cable signal mismatch')
            model_net = semantic.SIGNAL_NETS[left_label]
            semantic_row = semantic_rows[(cable['part'], from_pin, to_pin)]
            cable_rows.append(dict(cable=cable['part'], from_connector=left,
                                   from_pin=from_pin, to_connector=right,
                                   to_pin=to_pin, source_signal=left_label,
                                   model_net=model_net,
                                   from_export_net=actual[left].get(from_pin),
                                   to_export_net=actual[right].get(to_pin),
                                   from_functional_board_net_present=semantic_row['horizontal_board_net_present'],
                                   to_functional_board_net_present=semantic_row['destination_board_net_present']))
    if len(cable_rows) != 18 or len({row['cable'] for row in cable_rows}) != 4:
        raise ValueError('incomplete page-18 board cable list')
    pair_misses = [row for row in cable_rows
                   if row['from_export_net'] != row['model_net']
                   or row['to_export_net'] != row['model_net']]
    return dict(format='dac-monitor-page18-board-cable-pin-comparison-v2',
                qualification='all 18 labelled board-cable pairs checked at both physical pins; functional gaps and panel paths remain open',
                source_sha256=sha(SOURCE), source_pdf_sha256=pdf_sha256,
                assembly_sha256=sha(ASSEMBLY),
                sheet_sha256={stem: sha(ROOT/'circuits'/(stem+'.kicad_sch'))
                              for stem in sorted(set(SHEETS.values()))},
                cable_pairs_checked=len(cable_rows), labelled_connector_pins_checked=36,
                page16_neck_x1_4_checked=True,
                cable_pairs=cable_rows, pin_misses=pin_misses,
                extra_kicad_connector_pins=extras,
                functional_board_nets_both_present=semantic_report['both_board_nets'],
                functional_model_scope_gaps=semantic_report['missing_board_nets'],
                open_checks=['three cable signal kinds have functional model-scope gaps',
                             'panel topology and X1 physical pins are checked separately; connected contrast stage remains open',
                             'T3 internal winding order is outside this page-18 cable map'],
                passed=not pin_misses and not extras and not pair_misses)


def run(source_pdf):
    source = json.loads(SOURCE.read_text())
    if sha(source_pdf) != source['source']['pdf_sha256']:
        raise ValueError('source PDF differs from independent page-18 reading')
    assembly = json.loads(ASSEMBLY.read_text())
    with tempfile.TemporaryDirectory() as directory:
        output = Path(directory)/'assembly'
        model = steady_supply.assemble(output)
        exports = {connector: output/(stem+'.xml') for connector, stem in SHEETS.items()}
        return compare(source, assembly, exports, model['components'],
                       pdf_sha256=sha(source_pdf))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-pdf', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = run(args.source_pdf)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2)+'\n')
    print(f"{len(report['cable_pairs'])-len(report['pin_misses'])}/18 board cable pairs match; "
          f"{len(report['functional_model_scope_gaps'])} functional scope gaps")
    return 0 if report['passed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
