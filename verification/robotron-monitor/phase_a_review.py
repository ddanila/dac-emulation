"""Prepare and validate agent source readings required by Phase A A1.

An open inventory entry needs two independent readings or a bounded typical
value. All decisions remain bound to the inventory and source PDF hashes.
"""
import argparse
import hashlib
import json
import math
import re
from pathlib import Path

import inventory_audit

ROOT = Path(__file__).resolve().parent
SOURCES = ROOT / 'sources.json'
SCHEMATIC_PAGES = (3, 4, 9, 10, 16, 18)
DECISIONS = frozenset(('inventory-correct', 'inventory-corrected', 'class-typical'))
HEX_SHA256 = re.compile(r'[0-9a-f]{64}')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     ensure_ascii=False).encode()).hexdigest()


def source_hash():
    sources = json.loads(SOURCES.read_text())['sources']
    return next(item['sha256'] for item in sources if item['file'] == 'older.pdf')


def kicad_tree_hash():
    sha = hashlib.sha256()
    paths = sorted((ROOT / 'circuits').glob('*.kicad_sch'))
    if not paths:
        raise ValueError('KiCad schematic tree is missing')
    for path in paths:
        sha.update(path.name.encode())
        sha.update(path.read_bytes())
    return sha.hexdigest()


def converter_only_ids():
    """Scope out parts drawn only on the excluded converter or power input."""
    import steady_supply
    circuits = ROOT / 'circuits'
    excluded = ('k7222-11-converter.kicad_sch', 'k7222-11-power-input.kicad_sch')
    used = set()
    excluded_ids = set()
    for name in excluded:
        path = circuits / name
        ids = set(re.findall(r'\(property "SourceId" "([^"]+)"', path.read_text()))
        excluded_ids.update(ids)
    for name, _, _ in steady_supply.assembly_sheets():
        path = circuits / name
        ids = set(re.findall(r'\(property "SourceId" "([^"]+)"', path.read_text()))
        used.update(ids)
    return excluded_ids - used


def template(inventory, audit):
    by_id = {part['id']: part for part in inventory['parts']}
    excluded = converter_only_ids()
    return dict(format='dac-monitor-phase-a-source-review-v2',
                instruction='Record independent source readings or bounded typical values; blank fields are not decisions.',
                parts=[dict(id=entry['id'], source_page=entry['source_page'],
                            frame_path=entry['id'] not in excluded,
                            inventory_value=by_id[entry['id']].get('value'),
                            inventory_unit=by_id[entry['id']].get('unit'),
                            inventory_description=entry['inventory_description'],
                            ocr_status=entry['status'],
                            review_only_passes=entry.get('review_only_passes', []),
                            source_conflict=entry.get('source_conflict'),
                            ocr_readings=entry.get('readings', {}),
                            inventory_entry_sha256=digest(by_id[entry['id']]),
                            source_pdf_sha256=source_hash(),
                            decision=None, reading=None, independent_reads=[],
                            crop_sha256=None, argument=None, typical_value=None,
                            typical_bounds=None, typical_source=None)
                       for entry in audit['entries'] if entry['status'] != 'confirmed-by-3-passes'],
                schematics=[dict(source_page=page, source_pdf_sha256=source_hash(),
                                 kicad_tree_sha256=kicad_tree_hash(),
                                 independent_netlist_sha256=None,
                                 connectivity_checked=False,
                                 diode_direction_checked=False, winding_polarity_checked=False,
                                 argument=None)
                            for page in SCHEMATIC_PAGES])


def _nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def _agent_read(mark):
    reads = mark.get('independent_reads')
    if not isinstance(reads, list) or len(reads) < 2 or not _nonempty(mark.get('reading')):
        return False
    if not HEX_SHA256.fullmatch(mark.get('crop_sha256') or ''):
        return False
    identities = set()
    for read in reads:
        if not isinstance(read, dict) or not all(_nonempty(read.get(k)) for k in ('reading', 'method')):
            return False
        crop = read.get('crop_sha256')
        if not isinstance(crop, str) or not HEX_SHA256.fullmatch(crop):
            return False
        if read['reading'].strip() != mark['reading'].strip():
            return False
        identities.add((crop, read['method'], digest(read.get('resolution_px'))))
    return len(identities) >= 2 and mark['crop_sha256'] in {r['crop_sha256'] for r in reads}


def _typical(mark):
    bounds = mark.get('typical_bounds')
    value = mark.get('typical_value')
    return (type(value) in (int, float) and math.isfinite(value)
            and isinstance(bounds, list) and len(bounds) == 2
            and all(type(x) in (int, float) and math.isfinite(x) for x in bounds)
            and bounds[0] <= value <= bounds[1]
            and _nonempty(mark.get('typical_source')))


def evaluate(inventory, audit, marks):
    if audit.get('format') != 'dac-monitor-inventory-ocr-audit-v1':
        raise ValueError('invalid inventory audit format')
    if len(inventory['parts']) != 260 or len(audit.get('entries', [])) != 260:
        raise ValueError('review requires all 260 inventory entries')
    ids = [entry['id'] for entry in audit['entries']]
    if len(set(ids)) != 260 or set(ids) != {part['id'] for part in inventory['parts']}:
        raise ValueError('audit does not cover the current inventory')
    by_part = {part['id']: part for part in inventory['parts']}
    for entry in audit['entries']:
        part = by_part[entry['id']]
        if (entry['source_page'] != part['source']['page']
                or entry['inventory_description'] != part['description']
                or entry['inventory_evidence'] != part['evidence']):
            raise ValueError('audit is stale relative to the current inventory')
    if marks.get('format') != 'dac-monitor-phase-a-source-review-v2':
        raise ValueError('invalid agent-review format')
    part_marks = marks.get('parts', [])
    schematic_marks = marks.get('schematics', [])
    if not isinstance(part_marks, list) or not isinstance(schematic_marks, list):
        raise ValueError('review marks must be lists')
    if any(not isinstance(mark, dict) for mark in part_marks + schematic_marks):
        raise ValueError('review marks must be objects')
    if len({mark.get('id') for mark in part_marks}) != len(part_marks):
        raise ValueError('duplicate inventory review mark')
    if len({mark.get('source_page') for mark in schematic_marks}) != len(schematic_marks):
        raise ValueError('duplicate schematic review mark')
    by_mark = {mark.get('id'): mark for mark in part_marks}
    if set(by_mark) - set(ids):
        raise ValueError('review marks contain an unknown inventory entry')
    required = [entry for entry in audit['entries'] if entry['status'] != 'confirmed-by-3-passes']
    source = source_hash()
    excluded = converter_only_ids()
    open_parts = []
    resolved_parts = []
    for entry in required:
        mark = by_mark.get(entry['id'], {})
        valid = (mark.get('source_page') == entry['source_page']
                and mark.get('frame_path') is (entry['id'] not in excluded)
                and mark.get('source_pdf_sha256') == source
                and mark.get('inventory_entry_sha256') == digest(by_part[entry['id']])
                and mark.get('decision') in DECISIONS
                and _nonempty(mark.get('argument'))
                and (_typical(mark) if mark.get('decision') == 'class-typical'
                     else _agent_read(mark)))
        if valid:
            resolved_parts.append(entry['id'])
        elif entry['id'] not in excluded:
            open_parts.append(entry['id'])
    by_page = {mark.get('source_page'): mark for mark in schematic_marks}
    open_schematics = []
    kicad_hash = kicad_tree_hash()
    for page in SCHEMATIC_PAGES:
        mark = by_page.get(page, {})
        if not (mark.get('source_pdf_sha256') == source
                and mark.get('kicad_tree_sha256') == kicad_hash
                and isinstance(mark.get('independent_netlist_sha256'), str)
                and HEX_SHA256.fullmatch(mark['independent_netlist_sha256'])
                and all(mark.get(key) is True for key in ('connectivity_checked',
                    'diode_direction_checked', 'winding_polarity_checked'))
                and _nonempty(mark.get('argument'))):
            open_schematics.append(page)
    return dict(format='dac-monitor-phase-a-source-review-gate-v2',
                inventory_entries=260, machine_confirmed=260-len(required),
                agent_resolved=len(resolved_parts),
                frame_path_open_parts=open_parts,
                converter_only_unresolved=[entry['id'] for entry in required
                                           if entry['id'] in excluded and entry['id'] not in resolved_parts],
                open_parts=open_parts, open_schematics=open_schematics,
                passed=not open_parts and not open_schematics)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ocr-root', type=Path, required=True)
    parser.add_argument('--source-pdf', type=Path, required=True)
    parser.add_argument('--template', type=Path)
    parser.add_argument('--marks', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if bool(args.template) == bool(args.marks) or (args.marks and not args.output):
        parser.error('choose --template, or --marks with --output')
    if hashlib.sha256(args.source_pdf.read_bytes()).hexdigest() != source_hash():
        raise ValueError('schematic PDF hash differs from sources.json')
    inventory = json.loads(inventory_audit.INVENTORY.read_text())
    audit = inventory_audit.audit(inventory, args.ocr_root)
    if args.template:
        result = template(inventory, audit)
        destination = args.template
    else:
        result = evaluate(inventory, audit, json.loads(args.marks.read_text()))
        destination = args.output
    destination.parent.mkdir(parents=True, exist_ok=True)
    if args.template:
        with destination.open('x') as stream:
            stream.write(json.dumps(result, indent=2, ensure_ascii=False) + '\n')
    else:
        destination.write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n')
    if args.marks:
        print(json.dumps({key: result[key] for key in ('machine_confirmed','agent_resolved',
                                                      'open_parts','open_schematics','passed')}))
        return 0 if result['passed'] else 2
    print(f"Review template contains {len(result['parts'])} parts and {len(result['schematics'])} schematic pages")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
