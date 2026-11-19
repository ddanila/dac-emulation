"""Audit page-18 panel-control topology against the assembled SPICE deck."""
import argparse
import hashlib
import json
from pathlib import Path
import tempfile

import steady_supply
import transformer_candidates

ROOT = Path(__file__).resolve().parent
READ = ROOT/'reference/k7222-11/page18-panel-source-read.json'
INTERCONNECT = ROOT/'reference/k7222-11/page18-interconnect-transcription.json'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def resistor_lines(deck, prefix):
    rows = []
    for line in deck.splitlines():
        tokens = line.split()
        if tokens and tokens[0].startswith(prefix):
            if len(tokens) != 4:
                raise ValueError('invalid assembled control element: '+line)
            rows.append(dict(element=tokens[0], from_node=tokens[1],
                             to_node=tokens[2], resistance=tokens[3]))
    return rows


def compare(source, interconnect, deck, metadata, *, pdf_sha256):
    if source.get('format') != 'dac-monitor-page18-panel-source-read-v1':
        raise ValueError('unsupported panel source read')
    if source['source_pdf_sha256'] != pdf_sha256 or interconnect['source']['pdf_sha256'] != pdf_sha256:
        raise ValueError('source read and page-18 transcription use different PDFs')
    connector = interconnect['connectors']['012-6921:X1']
    for name in ('R1', 'R2'):
        control = source['controls'][name]
        if control['page18_terminals'] != interconnect['connectors']['panel:'+name]:
            raise ValueError('panel terminal read differs from page-18 transcription')
        if any(connector[pin] != label for terminal, label in control['page18_terminals'].items()
               for pin in [control['main_board_pins'][terminal]]):
            raise ValueError('panel terminal disagrees with main-board connector pin')
    r1 = source['controls']['R1']
    r2 = source['controls']['R2']
    if (r1['effective_external_terminals'], r1['wiper_tied_to_end']) != (3, False):
        raise ValueError('unexpected R1 source topology')
    if (r2['effective_external_terminals'], r2['wiper_tied_to_end']) != (2, True):
        raise ValueError('unexpected R2 source topology')
    brightness = resistor_lines(deck, 'Rbrightness_')
    contrast = resistor_lines(deck, 'Rcontrast_')
    terminal_nodes = metadata['external_brightness']['terminal_nodes']
    expected_brightness = {'E_35P': 'p35', 'S_HRS': 'collector_i',
                           'A_HRA': 'contrast_adjust'}
    r1_match = (terminal_nodes == expected_brightness and
                {(row['from_node'], row['to_node']) for row in brightness} ==
                {('p35', 'collector_i'), ('collector_i', 'contrast_adjust')})
    contrast_nodes = sorted({node for row in contrast
                             for node in (row['from_node'], row['to_node'])})
    r2_match = len(contrast) == 1 and len(contrast_nodes) == 2
    mismatches = []
    if not r1_match:
        mismatches.append('assembled R1 segments do not match the source E/S/A terminal order')
    if not r2_match:
        mismatches.append('source R2 is a two-wire KRA/KRS rheostat, but the assembled '
                          f'contrast network has {len(contrast)} elements and '
                          f'{len(contrast_nodes)} distinct nodes')
    return dict(format='dac-monitor-page18-panel-topology-comparison-v1',
                qualification='partial source-to-deck comparison; no physical X1 pin export or board-side KRA/KRS netlist yet',
                source_read_sha256=sha(READ), interconnect_sha256=sha(INTERCONNECT),
                source_pdf_sha256=pdf_sha256, model_sha256=sha(ROOT/'steady_supply.py'),
                source_r1_terminals=r1['page18_terminals'],
                source_r2_terminals=r2['page18_terminals'],
                source_r2_wiper_tied_to_end=True,
                brightness_model_elements=brightness, brightness_terminal_nodes=terminal_nodes,
                brightness_topology_matches=r1_match,
                contrast_model_elements=contrast, contrast_model_nodes=contrast_nodes,
                contrast_topology_matches=r2_match,
                mismatches=mismatches,
                open_checks=['trace KRA and KRS to board component pins on pages 3/4',
                             'compare main-board X1 physical pins with a fresh KiCad export',
                             *(['replace the three-node contrast divider with the source-connected rheostat']
                               if not r2_match else []),
                             'check the corrected contrast control in an assembled stage'],
                page18_gate_closed=False)


def run(source_pdf):
    source = json.loads(READ.read_text())
    if sha(source_pdf) != source['source_pdf_sha256']:
        raise ValueError('source PDF differs from panel read')
    interconnect = json.loads(INTERCONNECT.read_text())
    with tempfile.TemporaryDirectory() as directory:
        assembly = steady_supply.assemble(Path(directory)/'assembly')
        selection = {'status': 'complete', 'period_ticks': 3600000,
                     'clock_hz': 179712000, 'events': [[0, 0, 1, 1], [1800000, 1, 0, 1]]}
        candidate = transformer_candidates.enumerate_candidates(assembly['magnetic_graph'])[0]
        deck, metadata = steady_supply.deck(assembly, selection, candidate)
    return compare(source, interconnect, deck, metadata, pdf_sha256=sha(source_pdf))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-pdf', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = run(args.source_pdf)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2)+'\n')
    print('R1 topology '+('matches' if report['brightness_topology_matches'] else 'differs')+
          '; R2 '+('matches' if report['contrast_topology_matches'] else 'has an open mismatch'))


if __name__ == '__main__':
    main()
