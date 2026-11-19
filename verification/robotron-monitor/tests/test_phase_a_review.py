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

    def test_review_gate_accepts_independent_agent_readings_and_schematic_audit(self):
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
        marks['parts'][0].update(decision='inventory-correct', reading='source value matches inventory',
                                 argument='Inspected the printed component row.', crop_sha256='a'*64,
                                 independent_reads=[
                                     {'reading':'source value matches inventory','method':'vision crop',
                                      'crop_sha256':'a'*64,'resolution_px':1200},
                                     {'reading':'source value matches inventory','method':'classic OCR',
                                      'crop_sha256':'b'*64,'resolution_px':600}])
        for schematic in marks['schematics']:
            schematic.update(independent_netlist_sha256='c'*64, connectivity_checked=True,
                             diode_direction_checked=True, winding_polarity_checked=True,
                             argument='Independent pin list agrees with the schematic export.')
        complete = phase_a_review.evaluate(self.inventory, self.audit, marks)
        self.assertTrue(complete['passed'])
        self.assertEqual(complete['machine_confirmed'], 259)
        self.assertEqual(complete['agent_resolved'], 1)
        marks['parts'][0]['independent_reads'][0]['resolution_px'] = [1200, 1800]
        marks['parts'][0]['independent_reads'][1]['resolution_px'] = [600, 900]
        self.assertTrue(phase_a_review.evaluate(self.inventory, self.audit, marks)['passed'])
        stale = copy.deepcopy(marks)
        stale['parts'][0]['inventory_entry_sha256'] = '0' * 64
        self.assertFalse(phase_a_review.evaluate(self.inventory, self.audit, stale)['passed'])
        stale = copy.deepcopy(marks)
        stale['parts'][0]['decision'] = 'class-typical'
        self.assertFalse(phase_a_review.evaluate(self.inventory, self.audit, stale)['passed'])
        stale = copy.deepcopy(marks)
        stale['parts'][0]['independent_reads'][1]['reading'] = 'different value'
        self.assertFalse(phase_a_review.evaluate(self.inventory, self.audit, stale)['passed'])
        stale = copy.deepcopy(marks)
        stale['schematics'][0]['kicad_tree_sha256'] = '0' * 64
        self.assertFalse(phase_a_review.evaluate(self.inventory, self.audit, stale)['passed'])

    def test_bounded_typical_value_is_allowed_without_a_person(self):
        marks = phase_a_review.template(self.inventory, self.audit)
        marks['parts'][0].update(decision='class-typical', argument='Value is typical for this role.',
                                 typical_value=10, typical_bounds=[5, 15],
                                 typical_source='Documented comparable part')
        result = phase_a_review.evaluate(self.inventory, self.audit, marks)
        self.assertEqual(result['agent_resolved'], 1)
        self.assertEqual(result['open_parts'], [])
        marks['parts'][0]['typical_value'] = 20
        self.assertEqual(phase_a_review.evaluate(self.inventory, self.audit, marks)['open_parts'],
                         [self.audit['entries'][0]['id']])

    def test_converter_only_part_is_reported_without_blocking_frame_path(self):
        self.assertIn('012-6931:V22', phase_a_review.converter_only_ids())
        self.assertNotIn('012-6921:T3', phase_a_review.converter_only_ids())
        self.audit['entries'][0]['status'] = 'confirmed-by-3-passes'
        converter = next(entry for entry in self.audit['entries'] if entry['id'] == '012-6931:V22')
        converter['status'] = 'needs-source-review'
        marks = phase_a_review.template(self.inventory, self.audit)
        report = phase_a_review.evaluate(self.inventory, self.audit, marks)
        self.assertEqual(report['open_parts'], [])
        self.assertEqual(report['converter_only_unresolved'], ['012-6931:V22'])
        self.assertEqual(report['open_schematics'], list(phase_a_review.SCHEMATIC_PAGES))

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
