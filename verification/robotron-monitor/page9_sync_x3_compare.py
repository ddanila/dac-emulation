"""Audit page-9 handwritten X3:7 against the printed page-18 X3:6 cable map."""
import argparse
import hashlib
import json
from pathlib import Path

import page18_vertical_cable_compare as cable
import page9_sync_input_compare as sync_input

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / 'reference/k7222-11/page9-sync-x3-source-read.json'
WORKTREE = ROOT.parent.parent


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(source_pdf):
    source = json.loads(SOURCE.read_text())
    if source.get('format') != 'dac-monitor-page9-sync-x3-source-read-v1':
        raise ValueError('unknown X3 source read')
    if sha(source_pdf) != source['source_pdf']['sha256']:
        raise ValueError('schematic PDF differs from source read')
    for view in [*source['page9']['views'], source['page18']['view']]:
        if sha(WORKTREE / view['path']) != view['sha256']:
            raise ValueError('source view differs from recorded read: ' + view['path'])
    if sha(ROOT / source['page18']['transcription']) != source['page18']['transcription_sha256']:
        raise ValueError('page-18 transcription changed')

    page9 = source['page9']
    page18 = source['page18']
    if (page9['handwritten_connector'] != '012-6931:X3'
            or page9['handwritten_pin'] != '7'
            or page9['printed_signal'] != 'SYN'
            or page18['assembly_connector'] != page9['handwritten_connector']
            or page18['assembly_pin'] != '6'
            or page18['printed_signal'] != 'SYN'
            or page18['cable_part'] != cable.CABLE):
        raise ValueError('source-side X3 conflict changed')

    transcription = json.loads(cable.SOURCE.read_text())
    labels = transcription['connectors'][page18['assembly_connector']]
    cable_rows = [row for row in transcription['cables']
                  if row['part'] == page18['cable_part']]
    if (set(labels) != set('123456') or labels['6'] != 'SYN'
            or len(cable_rows) != 1
            or cable_rows[0]['from'] != page18['cable_from']
            or cable_rows[0]['to'] != page18['assembly_connector']
            or [page18['cable_from_pin'], page18['assembly_pin']]
            not in cable_rows[0]['pin_pairs']):
        raise ValueError('page-18 X3 connector or cable source disagrees')

    cable_report = cable.run(source_pdf)
    sync_report = sync_input.run(source_pdf)
    pin6 = [row for row in cable_report['pin_pairs']
            if row['to_pin'] == page18['assembly_pin']]
    if (not cable_report['passed'] or len(pin6) != 1
            or pin6[0]['source_signal'] != 'SYN'
            or pin6[0]['vertical_board_net'] != 'sync_gate'
            or cable_report['extra_kicad_pins'][page18['assembly_connector']]
            or not sync_report['passed']):
        raise ValueError('fresh KiCad X3 cable or R3 sync-input comparison failed')

    return {
        'format': 'dac-monitor-page9-sync-x3-comparison-v1',
        'qualification': 'confirmed cross-page source-label conflict; model follows printed page-18 six-pin assembly, but the page-9 handwritten 7 remains an open A1 annotation',
        'source_read_sha256': sha(SOURCE),
        'page18_transcription_sha256': sha(cable.SOURCE),
        'page18_cable_sheet_sha256': cable_report['sheet_sha256'],
        'page9_sync_input_sheet_sha256': sync_report['sheet_sha256'],
        'page9_handwritten': {'connector': page9['handwritten_connector'],
                              'pin': page9['handwritten_pin'], 'signal': 'SYN'},
        'page18_assembly': {'connector': page18['assembly_connector'],
                            'pin': page18['assembly_pin'], 'signal': 'SYN',
                            'cable_part': page18['cable_part']},
        'model_connector_pin6_net': pin6[0]['vertical_board_net'],
        'model_has_connector_pin7': '7' in cable_report['extra_kicad_pins'][page18['assembly_connector']],
        'page18_six_wire_cable_passed': cable_report['passed'],
        'page9_r3_sync_input_passed': sync_report['passed'],
        'source_conflict_open': True,
        'a1_page9_closed': False,
        'model_disposition': 'Retain X3:6 for the .11 six-wire assembly; do not claim that page-9 handwritten X3:7 agrees with it.',
        'next_action': 'Correct waveform-register mapping provenance and source-bound the page-9 annotation or carry it as a revision alternative during the whole-page netlist review.'
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-pdf', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = run(args.source_pdf)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print('page-9 X3:7 versus page-18 X3:6: source conflict confirmed')
