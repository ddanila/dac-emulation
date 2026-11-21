"""Compare a source-read page-9 A2 crossing with a fresh KiCad assembly."""
import argparse
import hashlib
import json
import tempfile
from pathlib import Path

import steady_supply

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / 'reference/k7222-11/page9-integrator-crossing-source-read.json'
SHEET = ROOT / 'circuits/k7222-11-vertical-integrator.kicad_sch'


def compare(source, components):
    if source.get('format') != 'dac-monitor-page9-integrator-crossing-source-read-v1':
        raise ValueError('page-9 crossing source read changed')
    expected_nets = {
        'A2_INVERTING': ['A2:7', 'R34:left', 'C22:left'],
        'HEIGHT_TRIM': ['R34:right', 'R35:left'],
        '00': ['R35:right', 'R35:wiper'],
        'RAMP_FEEDBACK': ['C22:right'],
    }
    if source['source_nets'] != expected_nets or 'without junction dots' not in source['crossing_read']:
        raise ValueError('source crossing terminals require a new independent read')
    by_id = {component['source_id']: component for component in components}
    ids = {name: '012-6931:' + name for name in ('A2', 'R34', 'R35', 'C22')}
    if not all(source_id in by_id for source_id in ids.values()):
        raise ValueError('a source-read page-9 part is absent from the assembly')
    actual = {name: by_id[source_id]['nodes'] for name, source_id in ids.items()}
    expected = {
        'R34': ['ramp_inv', 'height_trim'],
        'R35': ['height_trim', '0'],
        'C22': ['ramp_inv', 'vertical_ramp'],
    }
    matches = (all(actual[name] == nodes for name, nodes in expected.items())
               and len(actual['A2']) == 10 and actual['A2'][1] == 'ramp_inv')
    if not matches:
        raise ValueError('page-9 A2 crossing differs from the exported netlist')
    if any('p12' in actual[name] for name in ('R34', 'R35', 'C22')):
        raise ValueError('an isolated crossing touches 12P in the export')
    return {
        'format': 'dac-monitor-page9-integrator-crossing-comparison-v1',
        'qualification': 'scoped source-to-fresh-KiCad electrical comparison; physical R35 wiper is collapsed in the model and the full page-9 review stays open',
        'source_read_sha256': hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        'integrator_sheet_sha256': hashlib.sha256(SHEET.read_bytes()).hexdigest(),
        'source_nets': source['source_nets'],
        'assembled_nodes': actual,
        'electrical_crossing_matches': matches,
        'source_physical_terminals': 8,
        'assembled_electrical_terminals': 7,
        'physical_scope_gap': 'R35 wiper is tied to its right-hand end at 00 in the source, but the KiCad variable-resistance equivalent exports only two R35 pins.',
        'remaining': ['Preserve or explicitly reconcile the physical R35 wiper in the full pin-to-pin page-9 comparison.',
                      'Complete the independent source netlist and functional checks for the rest of page 9.'],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as directory:
        assembly = steady_supply.assemble(Path(directory) / 'assembly')
    report = compare(json.loads(SOURCE.read_text()), assembly['components'])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print('page-9 A2 crossing: electrical nets match; R35 physical wiper remains open')


if __name__ == '__main__':
    main()
