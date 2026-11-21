"""Expose the current T3 model's page-4 terminal-identity contradiction."""

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
REF = ROOT / 'reference/k7222-11'
SOURCE = REF / 'page4-t3-terminal-identity-source-read.json'
OLD_READ = REF / 't3-hv-terminal-read.json'
TRANSCRIPTION = REF / 'horizontal-output-transcription.json'
GRAPH = REF / 't3-winding-hypothesis.json'
OUTPUT = REF / 'page4-t3-terminal-identity-audit.json'
SOURCE_PDF = ROOT.parents[1] / 'build/monitor/phase-a/sources/older.pdf'
SOURCE_PAGE = ROOT.parents[1] / 'build/monitor/phase-a/sources/older-page4-600.png'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def audit(source, old_read, transcription, graph):
    if source['format'] != 'dac-monitor-page4-t3-terminal-identity-source-read-v1':
        raise ValueError('wrong terminal-identity read')
    labels = source['visible_labels']
    if labels != {
        'v21_anode_pad': 'X3:1', 'v21_cathode_pad': 'X3:2',
        'v21_cathode_net': 'EHT/UG3',
        't3_upper_right_bank': ['X1:1', 'X1:2', 'X1:3', 'X1:5', 'X1:7'],
    } or source['drawn_conductor_pairs'] != [['X1:2', 'X2:3']]:
        raise ValueError('source terminal labels or conductor read changed')
    ports = transcription['ports']
    t3_nodes = next(part['nodes'] for part in transcription['components']
                    if part['source_id'] == '012-6921:T3')
    if len(ports) != len(t3_nodes):
        raise ValueError('T3 port and node counts differ')
    model = dict(zip(ports, t3_nodes))
    v21 = next(part['nodes'] for part in transcription['components']
               if part['source_id'] == '012-6921:V21')
    upper = next(group['taps'] for group in graph['groups'] if group['id'] == 'upper_taps')
    old_diode = next(edge for edge in old_read['source_edges'] if edge['kind'] == 'rectifier')
    mismatches = {
        'x1_2_missing_from_magnetic_ports': 'X1_2' not in ports,
        'x1_2_missing_from_upper_tap_group': 'X1_2' not in upper,
        'x1_3_tied_to_x2_3_instead': model['X1_3'] == model['X2_3'],
        'old_read_mislabels_v21_pads':
            old_diode['anode'] == 'X1:1' and old_diode['cathode'] == 'X1:2',
    }
    return {
        'format': 'dac-monitor-page4-t3-terminal-identity-audit-v1',
        'qualification': 'source-visible contradiction audit of the current 19-port candidate; no corrected electrical graph or simulation result',
        'source_pdf_sha256': source['source']['pdf_sha256'],
        'source_page_sha256': source['source']['full_page_600dpi_sha256'],
        'input_sha256': {str(path.relative_to(ROOT)): sha(path)
                         for path in (SOURCE, OLD_READ, TRANSCRIPTION, GRAPH, Path(__file__))},
        'visible_labels': labels,
        'drawn_conductor_pairs': source['drawn_conductor_pairs'],
        'current_model': {'port_count': len(ports), 'upper_tap_group': upper,
                          'x1_3_net': model['X1_3'], 'x2_3_net': model['X2_3'],
                          'v21_nets': v21, 'old_read_diode_pads': old_diode},
        'mismatches': mismatches,
        'migration_required': any(mismatches.values()),
        'consequence': ('The existing 19-port T3 stage and HV comparison use a '
                        'misidentified diode pad and omit the separate X1:2 '
                        'terminal. They cannot qualify the source-connected '
                        '.11 winding graph or a design-point ratio. Rebuild '
                        'the T3 wrapper/return and re-run affected screens.'),
        'unresolved': source['unresolved'],
    }


def run(source_pdf, source_page):
    source = json.loads(SOURCE.read_text())
    if sha(source_pdf) != source['source']['pdf_sha256']:
        raise ValueError('source PDF changed')
    if sha(source_page) != source['source']['full_page_600dpi_sha256']:
        raise ValueError('page-4 render changed')
    return audit(source, json.loads(OLD_READ.read_text()),
                 json.loads(TRANSCRIPTION.read_text()), json.loads(GRAPH.read_text()))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-pdf', type=Path, default=SOURCE_PDF)
    parser.add_argument('--source-page', type=Path, default=SOURCE_PAGE)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args()
    result = run(args.source_pdf, args.source_page)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(f"{sum(result['mismatches'].values())}/{len(result['mismatches'])} model mismatches exposed")
