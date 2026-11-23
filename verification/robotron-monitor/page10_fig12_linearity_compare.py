"""Compare operating-manual Fig. 12 linearity topology with a fresh export."""
import hashlib
import json
from pathlib import Path
import tempfile

import steady_supply

ROOT = Path(__file__).resolve().parent
WORKTREE = ROOT.parent.parent
SOURCE = ROOT / 'reference/k7222-11/page10-fig12-linearity-source-read.json'
REPORT = ROOT / 'reference/k7222-11/page10-fig12-linearity-comparison.json'
SHEET = ROOT / 'circuits/k7222-11-vertical-output.kicad_sch'
MANUAL = WORKTREE / 'build/monitor/phase-a/sources/older-operation.pdf'
VIEW = WORKTREE / 'build/monitor/phase-a/operation-fig12-page15-600.png'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def compare(components):
    source = json.loads(SOURCE.read_text())
    if source['format'] != 'dac-monitor-page10-fig12-linearity-source-read-v1':
        raise ValueError('source read changed')
    if source['source']['pdf_page'] != 15 or source['source']['figure'] != 12:
        raise ValueError('wrong manual figure')
    if sha(MANUAL) != source['source']['pdf_sha256'] or sha(VIEW) != source['source']['view_600dpi_sha256']:
        raise ValueError('manual source or view changed')
    expected_parts = ['C23', 'R59', 'R60', 'R52', 'R53', 'V24']
    if source['scope'] != {'board': '012-6931', 'parts': expected_parts}:
        raise ValueError('unexpected source scope')
    expected_nets = {
        'A2_7V15_REFERENCE': ['C23:upper', 'R59:reference', 'R60:reference'],
        'ZERO': ['C23:lower'],
        'R59_TO_R52': ['R59:output', 'R52:left'],
        'R60_TO_R53': ['R60:output', 'R53:left'],
        'LOWER_THRESHOLD': ['R52:right'],
        'UPPER_THRESHOLD': ['R53:right', 'V24:anode'],
        'A3_INVERTING': ['V24:cathode'],
    }
    if source['nets'] != expected_nets:
        raise ValueError('manual terminal read changed')
    terminals = [terminal for group in expected_nets.values() for terminal in group]
    if len(terminals) != 12 or len(set(terminals)) != 12:
        raise ValueError('incomplete or duplicate manual terminals')
    by_id = {part['source_id']: part for part in components}
    actual = {name: by_id['012-6931:' + name]['nodes'] for name in expected_parts}
    expected = {
        'C23': ['vertical_reference', '0'],
        'R59': ['vertical_reference', 'lin_r59'],
        'R60': ['vertical_reference', 'lin_r60'],
        'R52': ['lin_r59', 'threshold_lower'],
        'R53': ['lin_r60', 'threshold_upper'],
        'V24': ['threshold_upper', 'amp_inv'],
    }
    mismatches = {part: {'expected': expected[part], 'actual': actual[part]}
                  for part in expected if actual[part] != expected[part]}
    return {
        'format': 'dac-monitor-page10-fig12-linearity-comparison-v1',
        'qualification': '12 manual-figure terminals match the current model; C23 conflicts with board-schematic page 10 and physical wiring remains unresolved',
        'manual_read_sha256': sha(SOURCE), 'sheet_sha256': sha(SHEET),
        'parts_checked': len(expected), 'terminals_checked': len(terminals),
        'exported_nodes': actual, 'mismatches': mismatches,
        'passed': not mismatches,
        'source_conflict': 'The board-schematic page-10 scan joins C23 upper to A3 physical pin 6 (negative supply), not the A2 reference shown here.',
    }


if __name__ == '__main__':
    with tempfile.TemporaryDirectory() as directory:
        components = steady_supply.assemble(Path(directory) / 'assembly')['components']
    result = compare(components)
    REPORT.write_text(json.dumps(result, indent=2) + '\n')
    print(f"Fig. 12 linearity: {result['terminals_checked']} manual terminals; passed={result['passed']}")
    raise SystemExit(0 if result['passed'] else 2)
