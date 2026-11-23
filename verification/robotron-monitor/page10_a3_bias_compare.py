"""Compare the page-10 A3 positive-bias source branch with a fresh export."""
import argparse
import hashlib
import json
from pathlib import Path
import tempfile

import steady_supply

ROOT = Path(__file__).resolve().parent
WORKTREE = ROOT.parent.parent
SOURCE = ROOT/'reference/k7222-11/page10-a3-bias-source-netlist.json'
SHEET = ROOT/'circuits/k7222-11-vertical-output.kicad_sch'
VIEWS = ('build/monitor/phase-a/page10-600.png',
         'build/monitor/phase-a/page10-input-1200-crop.png')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def compare(components):
    source = json.loads(SOURCE.read_text())
    if source['format'] != 'dac-monitor-page10-a3-bias-source-netlist-v1':
        raise ValueError('A3 bias source read changed')
    if sha(WORKTREE/'build/monitor/phase-a/sources/older.pdf') != source['source']['pdf_sha256']:
        raise ValueError('source PDF changed')
    for path, view in zip(VIEWS, source['source']['views']):
        if sha(WORKTREE/path) != view['sha256']:
            raise ValueError('source view changed: '+path)
    expected = {
        'R37': ['p22', 'amp_vp'],
        'C17': ['amp_vp', '0'],
        'V14': ['zener_join', '0'],
        'V15': ['zener_join', 'amp_vp'],
    }
    source_nets = {
        '22P': ['R37:upper'],
        '00': ['C17:negative', 'V14:cathode'],
        'ZENER_JOIN': ['V14:anode', 'V15:anode'],
        'AMP_VP': ['R37:lower', 'C17:positive', 'V15:cathode'],
    }
    if source['scope']['parts'] != list(expected):
        raise ValueError('source scope changed')
    if source['nets'] != source_nets:
        raise ValueError('source net read changed')
    terminals = [terminal for net in source_nets.values() for terminal in net]
    if len(terminals) != 8 or len(set(terminals)) != 8:
        raise ValueError('source terminals incomplete')
    by_id = {part['source_id']: part for part in components}
    actual = {name: by_id['012-6931:'+name]['nodes'] for name in expected}
    if actual != expected:
        raise ValueError('A3 bias branch differs from source read')
    return {
        'format': 'dac-monitor-page10-a3-bias-comparison-v1',
        'qualification': 'four-part scoped source-to-fresh-export comparison; not page-10 or A3 functional signoff',
        'source_read_sha256': sha(SOURCE),
        'sheet_sha256': sha(SHEET),
        'parts_checked': 4,
        'terminals_checked': 8,
        'source_nets': source['nets'],
        'exported_nodes': actual,
        'diode_orientation_matches': True,
        'c17_source_positive_node': 'amp_vp',
        'c17_model_limitation': 'The generic SPICE capacitor has no polarity-dependent failure or leakage behavior.',
        'passed': True,
        'remaining': ['Identify and compare the adjacent upper-line capacitor and other uncovered page-10 parts.',
                      'Complete page-10 joins and vertical-stage functional checks.'],
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT/'reference/k7222-11/page10-a3-bias-comparison.json')
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as directory:
        components = steady_supply.assemble(Path(directory)/'assembly')['components']
    report = compare(components)
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    print('page-10 A3 bias: 8 source terminals match fresh export')
