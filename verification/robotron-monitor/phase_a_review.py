"""Prepare and validate the human source review required by Phase A A1.

OCR agreement is not a human mark. A mark is bound to one inventory entry and
the hashed .11/.21 schematic PDF; schematic review is recorded separately.
"""
import argparse
import hashlib
import json
import re
from datetime import date
from pathlib import Path

import inventory_audit

ROOT = Path(__file__).resolve().parent
SOURCES = ROOT / 'sources.json'
SCHEMATIC_PAGES = (3, 4, 9, 10, 16, 18)
DECISIONS = frozenset(('inventory-correct', 'inventory-corrected', 'unresolved'))


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


def template(inventory, audit):
    by_id = {part['id']: part for part in inventory['parts']}
    return dict(format='dac-monitor-phase-a-source-review-v1',
                instruction='Fill only from the hashed PDF and KiCad review; blank fields are not marks.',
                parts=[dict(id=entry['id'], source_page=entry['source_page'],
                            inventory_value=by_id[entry['id']].get('value'),
                            inventory_unit=by_id[entry['id']].get('unit'),
                            inventory_description=entry['inventory_description'],
                            ocr_status=entry['status'],
                            review_only_passes=entry.get('review_only_passes', []),
                            source_conflict=entry.get('source_conflict'),
                            ocr_readings=entry.get('readings', {}),
                            inventory_entry_sha256=digest(by_id[entry['id']]),
                            source_pdf_sha256=source_hash(),
                            decision=None, observed=None, rationale=None,
                            reviewer=None, reviewed_at=None)
                       for entry in audit['entries'] if entry['status'] != 'confirmed-by-3-passes'],
                schematics=[dict(source_page=page, source_pdf_sha256=source_hash(),
                                 kicad_tree_sha256=kicad_tree_hash(),
                                 kicad_commit=None, connectivity_checked=False,
                                 diode_direction_checked=False, winding_polarity_checked=False,
                                 reviewer=None, reviewed_at=None, notes=None)
                            for page in SCHEMATIC_PAGES])


def _identified(mark):
    if not (isinstance(mark.get('reviewer'), str) and mark['reviewer'].strip()
            and isinstance(mark.get('reviewed_at'), str)):
        return False
    try:
        date.fromisoformat(mark['reviewed_at'])
    except ValueError:
        return False
    return True


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
    if marks.get('format') != 'dac-monitor-phase-a-source-review-v1':
        raise ValueError('invalid human-review format')
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
    open_parts = []
    for entry in required:
        mark = by_mark.get(entry['id'], {})
        if not (mark.get('source_page') == entry['source_page']
                and mark.get('source_pdf_sha256') == source
                and mark.get('inventory_entry_sha256') == digest(by_part[entry['id']])
                and mark.get('decision') in DECISIONS
                and (mark.get('decision') != 'unresolved'
                     or by_part[entry['id']]['evidence'] == 'unresolved')
                and isinstance(mark.get('observed'), str) and mark['observed'].strip()
                and isinstance(mark.get('rationale'), str) and mark['rationale'].strip()
                and _identified(mark)):
            open_parts.append(entry['id'])
    by_page = {mark.get('source_page'): mark for mark in schematic_marks}
    open_schematics = []
    kicad_hash = kicad_tree_hash()
    for page in SCHEMATIC_PAGES:
        mark = by_page.get(page, {})
        if not (mark.get('source_pdf_sha256') == source
                and mark.get('kicad_tree_sha256') == kicad_hash
                and isinstance(mark.get('kicad_commit'), str)
                and re.fullmatch(r'[0-9a-f]{8,40}', mark['kicad_commit'])
                and all(mark.get(key) is True for key in ('connectivity_checked',
                    'diode_direction_checked', 'winding_polarity_checked'))
                and _identified(mark)):
            open_schematics.append(page)
    return dict(format='dac-monitor-phase-a-source-review-gate-v1',
                inventory_entries=260, machine_confirmed=260-len(required),
                human_marked=len(required)-len(open_parts),
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
        print(json.dumps({key: result[key] for key in ('machine_confirmed','human_marked',
                                                      'open_parts','open_schematics','passed')}))
        return 0 if result['passed'] else 2
    print(f"Review template contains {len(result['parts'])} parts and {len(result['schematics'])} schematic pages")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
