"""Regenerate corrected .11 T3 functional anchors without inventing HV polarity."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REF = ROOT / 'reference/k7222-11'
READS = {key: REF / name for key, name in {
    'drive': 't3-drive-polarity-source-read.json',
    'g1': 't3-g1-rectifier-source-read.json',
    'terminal_identity': 'page4-t3-terminal-identity-source-read.json',
    'visible_graph_candidate': 't3-page4-visible-graph.json',
    'tv_variant': 't3-tv-variant-source-read.json',
}.items()}
HISTORICAL = REF / 't3-functional-core-historical.json'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(source_pdf):
    pdf_hash = sha(source_pdf)
    data = {key: json.loads(path.read_text()) for key, path in READS.items()}
    drive, g1, identity, graph, variant = (data[key] for key in READS)
    if (drive['source_pdf_sha256'] != pdf_hash
            or g1['source_pdf_sha256'] != pdf_hash
            or identity['source']['pdf_sha256'] != pdf_hash):
        raise ValueError('source PDF differs from T3 functional reads')
    if (drive['source_edges']['drive_winding_endpoints'] != ['X2:7', 'X2:4']
            or drive['source_edges']['output_transistor_collector']['t3_terminal'] != 'X2:7'
            or drive['source_edges']['damper'] != dict(
                part='V17', anode_net='0', cathode_terminal='X2:7')):
        raise ValueError('source drive/damper terminals changed')
    if g1['source_edges'] != dict(v14_anode_net='h_g1raw',
            v14_cathode_t3_terminal='X2:6', c18_other_terminal='00',
            manual_tp17_terminal='V14:K'):
        raise ValueError('source G1 rectifier terminals changed')
    labels = identity['visible_labels']
    if (labels['v21_anode_pad'] != 'X3:1'
            or labels['v21_cathode_pad'] != 'X3:2'
            or labels['v21_cathode_net'] != 'EHT/UG3'
            or ['X1:2', 'X2:3'] not in identity['drawn_conductor_pairs']):
        raise ValueError('corrected V21 pads or external conductor changed')
    if graph['source_terminal_read_sha256'] != sha(READS['terminal_identity']):
        raise ValueError('visible graph is not bound to corrected source read')
    terminals = [pin.replace('_', ':') for group in graph['groups']
                 for pin in group['taps']]
    if (len(terminals) != len(set(terminals)) or len(terminals) != 20
            or 'X3:1' not in terminals or 'X1:16' in terminals):
        raise ValueError('source-visible T3 terminal inventory changed')
    bridges = {frozenset(pair) for pair in variant['reported_tv_bridges']}
    if bridges != {frozenset(('X1:1', 'X1:2')),
                   frozenset(('X1:7', 'X2:3'))}:
        raise ValueError('reported TV bridges changed')
    if 'V21 anode X3:1, cathode X3:2/EHT' not in variant['compatibility_with_k7222_11']['required_external_v21_path']:
        raise ValueError('TV comparison still uses superseded V21 pads')
    historical = json.loads(HISTORICAL.read_text())
    if (historical['voltage_reference']['high_voltage'] != 'V(X1:1)-V(X1:16)'
            or historical['source_read_sha256']['hv'] != sha(REF / 't3-hv-terminal-read.json')):
        raise ValueError('historical conditional result changed')
    return {
        'format': 'dac-monitor-t3-functional-anchors-v2',
        'status': 'incomplete: no source-qualified HV winding pair, ratio or sign selection',
        'qualification': 'corrected .11 external functional anchors only; no complete winding graph or design point',
        'source_pdf_sha256': pdf_hash,
        'source_read_sha256': {key: sha(path) for key, path in READS.items()},
        'historical_report_sha256': sha(HISTORICAL),
        'visible_magnetic_terminal_count': len(terminals),
        'functional_anchors': {
            'drive_visible_endpoints': ['X2:7', 'X2:4'],
            'collector_and_damper_cathode': 'X2:7',
            'v21_anode_t3_terminal': 'X3:1',
            'v21_cathode_rectified_terminal': 'X3:2',
            'v14_cathode_t3_terminal': 'X2:6',
            'drawn_external_conductor': ['X1:2', 'X2:3'],
        },
        'qualified_hv_cold_end': None,
        'qualified_hv_differential_sign': None,
        'qualified_g1_relative_sign': None,
        'conditional_g1_rule': 'If X2:5 is the 00 return and internally continuous with X2:6, collector flyback needs X2:6 negative relative to X2:5 for V14 to charge negative G1.',
        'tv_variant_disposition': 'Do not transfer the reported TV bridges to .11. The old V21-bypass exclusion is invalid because V21 is on X3:1/X3:2.',
        'historical_result_disposition': 'The archived 1-of-4 HV/G1 sign result depended on superseded X1:1/V21/X1:2 pads and manual-only X1:16; it cannot prune the corrected 20-port graph.',
        'unresolved': [
            'Identify or bound the winding return feeding V21 anode X3:1; X1:16 is not a visible page-4 terminal.',
            'Qualify X2:5 return, X2:5-X2:6 continuity and connected X2:4 drive before using the conditional G1 sign.',
            'Bound winding turns, polarities, loss and parasitics before an equivalent fallback can replace T3.'
        ],
        'audit_passed': True,
        'a5_qualified': False,
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-pdf', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = run(args.source_pdf)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print('T3 functional anchors checked; HV sign and A5 remain unqualified')
