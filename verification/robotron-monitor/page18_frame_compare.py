"""Compare page-18 cable labels with the ideal-rail KiCad assembly.

This is a semantic check of the four board-to-board cables, not a pin-level
A1 approval: a separate receipt checks all source-labelled physical pins.
"""
import argparse
import hashlib
import json
import tempfile
from pathlib import Path

import steady_supply

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT/'reference/k7222-11/page18-interconnect-transcription.json'
ASSEMBLY = ROOT/'reference/k7222-11/assembly.json'

FRAME_CABLES = {'1.11.017307.0', '1.11.017308.0',
                '1.11.017293.0', '1.11.017294.0'}
SCOPE_GAPS = {
    '41P': 'vertical-board converter supply path is excluded by ideal rails',
    'SYNCH': 'vertical-board converter synchronizing path is excluded with that converter',
    'INTENS': 'external intensity drive reaches the neck board without a main-board sheet component; connected stimulus remains unqualified',
    '10.7P': 'neck heater electrical branch is replaced by a held thermal state; sustained heater balance remains unqualified',
}
SIGNAL_NETS = {
    'UG1': 'ug1', 'UG2': 'ug2', 'UG4': 'ug4',
    'VID': 'vid', 'INTENS': 'intens', '10.7P': 'p10_7',
    '41P': 'p41', '00': '0', '5P': 'p5', '12P': 'p12',
    '22P': 'p22', 'SYN': 'sync_gate', 'SYNCH': 'h_sync',
    'X1': 'hy1', 'X2': 'hy2',
}


def compare(source, assembly, components):
    if source.get('format') != 'dac-monitor-interconnect-source-v1':
        raise ValueError('unsupported source transcription')
    if assembly.get('interconnect_transcription') != SOURCE.name:
        raise ValueError('assembly points to a different interconnect source')
    by_board = {
        board: {net for part in components if part['source_id'].startswith(board+':')
                for net in part['nodes']}
        for board in ('012-6921', '012-6931', '012-6891')
    }
    cable_rows = [c for c in source['cables'] if c['part'] in FRAME_CABLES]
    if {c['part'] for c in cable_rows} != FRAME_CABLES:
        raise ValueError('missing frame-path board cable')
    rows = []
    seen = set()
    for cable in cable_rows:
        if cable['from'] not in ('012-6921:X5', '012-6921:X4',
                                 '012-6921:X6', '012-6921:X3'):
            raise ValueError('unexpected source connector')
        if cable['to'] not in ('012-6931:X1', '012-6931:X3', '012-6891:X1'):
            raise ValueError('unexpected destination connector')
        destination_board = cable['to'].split(':', 1)[0]
        for from_pin, to_pin in cable['pin_pairs']:
            key = (cable['from'], from_pin, cable['to'], to_pin)
            if key in seen:
                raise ValueError('duplicate cable pair')
            seen.add(key)
            left = source['connectors'][cable['from']][from_pin]
            right = source['connectors'][cable['to']][to_pin]
            if left != right or left not in SIGNAL_NETS:
                raise ValueError(f'cable signal mismatch: {key}')
            model_net = SIGNAL_NETS[left]
            if destination_board == '012-6891' and assembly['neck_connectors']['X1'][to_pin] != model_net:
                raise ValueError(f'neck model pin differs from page 18: {key}')
            rows.append(dict(cable=cable['part'], from_connector=cable['from'],
                             from_pin=from_pin, to_connector=cable['to'],
                             to_pin=to_pin, source_signal=left,
                             model_net=model_net,
                             horizontal_board_net_present=model_net in by_board['012-6921'],
                             destination_board=destination_board,
                             destination_board_net_present=model_net in by_board[destination_board]))
    if len(rows) != 18:
        raise ValueError('expected eighteen frame-path cable pairs')
    gaps = [r for r in rows if not
            (r['horizontal_board_net_present'] and r['destination_board_net_present'])]
    if {row['source_signal'] for row in gaps} != set(SCOPE_GAPS):
        raise ValueError('board-net scope gaps changed; review their model disposition')
    return dict(format='dac-monitor-page18-frame-comparison-v2',
                qualification='semantic comparison with four explicitly classified functional model-scope gaps; physical pins checked in a separate receipt, connected contrast stage open',
                source_sha256=hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
                assembly_sha256=hashlib.sha256(ASSEMBLY.read_bytes()).hexdigest(),
                assembled_components_sha256=hashlib.sha256(
                    json.dumps(components, sort_keys=True).encode()).hexdigest(),
                cable_pairs=rows,
                both_board_nets=sum(r['horizontal_board_net_present'] and
                                    r['destination_board_net_present'] for r in rows),
                missing_board_nets=gaps,
                scope_gap_dispositions=SCOPE_GAPS,
                mapping_limits=['X1/X2 map to the current hy1/hy2 centring-choke and yoke nets; the separate yoke-pin comparison checks terminal labels, not winding polarity',
                                'SYNCH maps to the horizontal-output h_sync label; the vertical-board converter path is outside the ideal-rail frame'],
                open_checks=['four cable signals have classified functional model-scope gaps despite matching physical pins',
                             'panel topology and X1 physical pins are checked separately; connected contrast stage remains open'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as directory:
        model = steady_supply.assemble(Path(directory)/'assembly')
    report = compare(json.loads(SOURCE.read_text()), json.loads(ASSEMBLY.read_text()),
                     model['components'])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(dict(pairs=len(report['cable_pairs']),
                          both_board_nets=report['both_board_nets'],
                          missing=[r['source_signal'] for r in report['missing_board_nets']])))


if __name__ == '__main__':
    main()
