import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import inventory_audit
import phase_a_review


class PhaseAReviewTests(unittest.TestCase):
    def setUp(self):
        self.inventory = json.loads(inventory_audit.INVENTORY.read_text())
        self.audit = dict(format='dac-monitor-inventory-ocr-audit-v1',
                          entries=[dict(id=part['id'], source_page=part['source']['page'],
                                        inventory_description=part['description'],
                                        inventory_evidence=part['evidence'],
                                        status='confirmed-by-3-passes')
                                   for part in self.inventory['parts']])
        self.audit['entries'][0]['status'] = 'needs-source-review'

    def test_review_gate_requires_current_part_and_schematic_marks(self):
        marks = phase_a_review.template(self.inventory, self.audit)
        self.assertEqual(len(marks['parts']), 1)
        self.assertEqual(len(marks['schematics']), 6)
        self.assertEqual(marks['parts'][0]['inventory_description'],
                         self.audit['entries'][0]['inventory_description'])
        self.assertEqual(marks['parts'][0]['ocr_status'], 'needs-source-review')
        self.assertEqual(marks['parts'][0]['ocr_readings'], {})
        pending = phase_a_review.evaluate(self.inventory, self.audit, marks)
        self.assertFalse(pending['passed'])
        self.assertEqual(pending['open_parts'], [self.audit['entries'][0]['id']])
        self.assertEqual(pending['open_schematics'], list(phase_a_review.SCHEMATIC_PAGES))
        marks['parts'][0].update(decision='inventory-correct', observed='source value matches inventory',
                                 rationale='inspected the printed component row',
                                 reviewer='Source reviewer', reviewed_at='2026-11-18')
        for schematic in marks['schematics']:
            schematic.update(kicad_commit='ba538139', connectivity_checked=True,
                             diode_direction_checked=True, winding_polarity_checked=True,
                             reviewer='Schematic reviewer', reviewed_at='2026-11-18')
        complete = phase_a_review.evaluate(self.inventory, self.audit, marks)
        self.assertTrue(complete['passed'])
        self.assertEqual(complete['machine_confirmed'], 259)
        self.assertEqual(complete['human_marked'], 1)
        stale = copy.deepcopy(marks)
        stale['parts'][0]['inventory_entry_sha256'] = '0' * 64
        self.assertFalse(phase_a_review.evaluate(self.inventory, self.audit, stale)['passed'])
        stale = copy.deepcopy(marks)
        stale['parts'][0]['decision'] = 'unresolved'
        self.assertFalse(phase_a_review.evaluate(self.inventory, self.audit, stale)['passed'])
        stale = copy.deepcopy(marks)
        stale['parts'][0]['reviewed_at'] = '2026-99-99'
        self.assertFalse(phase_a_review.evaluate(self.inventory, self.audit, stale)['passed'])
        stale = copy.deepcopy(marks)
        stale['schematics'][0]['kicad_tree_sha256'] = '0' * 64
        self.assertFalse(phase_a_review.evaluate(self.inventory, self.audit, stale)['passed'])

    def test_stale_audit_and_duplicate_marks_are_rejected(self):
        marks = phase_a_review.template(self.inventory, self.audit)
        stale = copy.deepcopy(self.audit)
        stale['entries'][0]['inventory_description'] = 'changed'
        with self.assertRaisesRegex(ValueError, 'stale'):
            phase_a_review.evaluate(self.inventory, stale, marks)
        marks['parts'].append(copy.deepcopy(marks['parts'][0]))
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            phase_a_review.evaluate(self.inventory, self.audit, marks)


if __name__ == '__main__':
    unittest.main()
