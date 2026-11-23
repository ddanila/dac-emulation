"""Compare page-10 C24/R49 input branch with a fresh KiCad export."""
import hashlib
import json
from pathlib import Path
import tempfile

import steady_supply

ROOT = Path(__file__).resolve().parent
WORKTREE = ROOT.parent.parent
SOURCE = ROOT / 'reference/k7222-11/page10-symmetry-input-source-read.json'
REPORT = ROOT / 'reference/k7222-11/page10-symmetry-input-comparison.json'
SHEET = ROOT / 'circuits/k7222-11-vertical-output.kicad_sch'
SOURCE_PDF = WORKTREE / 'build/monitor/phase-a/sources/older.pdf'
VIEWS = [WORKTREE / 'build/monitor/phase-a/page10-output-lower-1200-crop.png',
         WORKTREE / 'build/monitor/phase-a/page10-feedback-left-1200-zoom.png']


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def compare(components):
    source = json.loads(SOURCE.read_text())
    if source['format'] != 'dac-monitor-page10-symmetry-input-source-read-v1':
        raise ValueError('source read format changed')
    if source['source']['page'] != 10 or source['scope'] != {'board': '012-6931',
                                                            'parts': ['C24', 'R49']}:
        raise ValueError('wrong source scope')
    if sha(SOURCE_PDF) != source['source']['pdf_sha256']:
        raise ValueError('source PDF changed')
    if len(source['source']['views']) != len(VIEWS):
        raise ValueError('source view count changed')
    for path, view in zip(VIEWS, source['source']['views']):
        if sha(path) != view['sha256']:
            raise ValueError('source view changed: ' + str(path))
    nets = {'ZERO': ['C24:upper'],
            'SYMMETRY': ['C24:lower', 'R49:left'],
            'A3_NONINVERTING': ['R49:right']}
    if source['nets'] != nets:
        raise ValueError('source terminals changed')
    by_id = {part['source_id']: part for part in components}
    actual = {name: by_id['012-6931:' + name]['nodes'] for name in ('C24', 'R49')}
    expected = {'C24': ['symmetry', '0'], 'R49': ['symmetry', 'amp_noninv']}
    mismatches = {name: {'expected': expected[name], 'actual': actual[name]}
                  for name in expected if actual[name] != expected[name]}
    return {'format': 'dac-monitor-page10-symmetry-input-comparison-v1',
            'qualification': 'four-terminal local A1 source-to-export check; full page 10 and operating point remain open',
            'source_read_sha256': sha(SOURCE), 'sheet_sha256': sha(SHEET),
            'parts_checked': 2, 'terminals_checked': 4,
            'source_nets': nets, 'exported_nodes': actual,
            'mismatches': mismatches, 'passed': not mismatches}


if __name__ == '__main__':
    with tempfile.TemporaryDirectory() as directory:
        components = steady_supply.assemble(Path(directory) / 'assembly')['components']
    result = compare(components)
    REPORT.write_text(json.dumps(result, indent=2) + '\n')
    print(f"page-10 C24/R49 input: {result['terminals_checked']} terminals; passed={result['passed']}")
    raise SystemExit(0 if result['passed'] else 2)
