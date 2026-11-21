"""Check the page-4 X1:1–X1:7 conductor against the opt-in T3 wrapper."""

import argparse
import hashlib
import json
from pathlib import Path

import page4_t3_visible_wrapper as wrapper


ROOT = Path(__file__).resolve().parent
WORKTREE = ROOT.parent.parent
SOURCE = ROOT / 'reference/k7222-11/page4-t3-upper-bridge-source-read.json'
OUTPUT = ROOT / 'reference/k7222-11/page4-t3-upper-bridge-audit.json'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(source_pdf):
    source = json.loads(SOURCE.read_text())
    if source['format'] != 'dac-monitor-page4-t3-upper-bridge-source-read-v1':
        raise ValueError('unknown upper bridge source read')
    if sha(source_pdf) != source['source_pdf']['sha256']:
        raise ValueError('page-4 PDF differs from upper bridge read')
    for view in source['views']:
        parent = WORKTREE / f"build/monitor/phase-a/page4-{view['resolution_dpi']}.png"
        if sha(parent) != view['parent_view_sha256']:
            raise ValueError('full-page view changed: ' + str(parent))
        if sha(WORKTREE / view['path']) != view['sha256']:
            raise ValueError('upper bridge view changed: ' + view['path'])
    if source['drawn_conductor_pair'] != ['X1:1', 'X1:7']:
        raise ValueError('upper bridge source pair changed')

    exported = wrapper.run(source_pdf)
    if not exported['passed']:
        raise ValueError('existing wrapper export failed its own scoped checks')
    nodes = exported['exported_nodes']
    if not nodes['X1_1'] or not nodes['X1_7']:
        raise ValueError('source-visible X1 terminals absent from export')
    tied = nodes['X1_1'] == nodes['X1_7']
    return {
        'format': 'dac-monitor-page4-t3-upper-bridge-audit-v1',
        'qualification': 'source-to-model external conductor comparison; no winding ratio or connected design point',
        'source_read_sha256': sha(SOURCE),
        'candidate_sheet_sha256': exported['candidate_sheet_sha256'],
        'source_pair': source['drawn_conductor_pair'],
        'exported_nets': {'X1:1': nodes['X1_1'], 'X1:7': nodes['X1_7']},
        'source_requires_same_net': True,
        'model_has_same_net': tied,
        'source_model_match': tied,
        'audit_passed': True,
        'a5_qualified': False,
        'next_action': 'Split/re-evaluate the assumed high-voltage winding group and join X1:1 to X1:7 in the opt-in 20-port interface; rerun source comparisons and affected connected screens.'
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-pdf', type=Path, default=WORKTREE / 'build/monitor/phase-a/sources/older.pdf')
    parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args()
    result = run(args.source_pdf)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print('X1:1–X1:7 source/model match:', result['source_model_match'])
