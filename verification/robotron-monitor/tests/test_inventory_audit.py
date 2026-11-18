import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import inventory_audit


class InventoryAuditTests(unittest.TestCase):
    def test_ranges_expand_and_inconsistent_ocr_is_not_agreement(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            text = ('Kurzzeichen,Stückzahl,Benennung,Sachnummer\n'
                    'R8:1 ...,3,Schichtwiderstand 160 Ohm,0.7121 2200.0/90\n'
                    'V7 ... 9,3,Diode 1 YL 1/1,1.15.951489.0/90\n'
                    '"V1, V6, V12",1,Diode 1 AE 15,1.15.951203.0/90\n')
            (root / 'page_007.csv').write_text(text)
            rows = list(inventory_audit._readings(root / 'page_007.csv'))
            self.assertEqual(rows[0]['references'], ['R8:1', 'R8:2', 'R8:3'])
            self.assertTrue(rows[0]['quantity_consistent'])
            self.assertEqual(rows[1]['references'], ['V7', 'V8', 'V9'])
            self.assertFalse(rows[2]['quantity_consistent'])

    def test_machine_agreement_is_checked_against_inventory(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            inventory = json.loads(inventory_audit.INVENTORY.read_text())
            for tag in ('', '.r300', '.alt'):
                (root / f'page_006{tag}.csv').write_text(
                    'Kurzzeichen,Stückzahl,Benennung,Sachnummer\n'
                    'A1,1,Integrierter Schaltkreis T 200,1.15.951651.0/90\n')
            report = inventory_audit.audit(inventory, root)
            point = next(e for e in report['entries'] if e['id'] == '012-6921:A1')
            self.assertEqual(point['exact_agreement_passes'], ['primary', 'r300', 'alt'])
            self.assertTrue(point['inventory_value_or_type_matches'])
            self.assertEqual(point['status'], 'confirmed-by-3-passes')
            self.assertEqual(report['inventory_entries'], 260)

    def test_different_stock_number_breaks_agreement(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            inventory = json.loads(inventory_audit.INVENTORY.read_text())
            for tag, article in (('', '1.15.951651.0/90'),
                                 ('.r300', '1.15.951651.0/90'),
                                 ('.alt', '1.15.951652.0/90')):
                (root / f'page_006{tag}.csv').write_text(
                    'Kurzzeichen,Stückzahl,Benennung,Sachnummer\n'
                    f'A1,1,Integrierter Schaltkreis T 200,{article}\n')
            report = inventory_audit.audit(inventory, root)
            point = next(e for e in report['entries'] if e['id'] == '012-6921:A1')
            self.assertEqual(len(point['exact_agreement_passes']), 2)
            self.assertEqual(point['status'], 'needs-source-review')

    def test_semicolon_delimited_vision_pass_is_parsed(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'page_006.alt.csv'
            path.write_text('Kurzzeichen;Stückzahl;Benennung;Sachnummer\n'
                            'C1, C3;2;KT-Kondensator 100/10/630;0.7745 3400.0/90\n')
            row = list(inventory_audit._readings(path))[0]
            self.assertEqual(row['references'], ['C1', 'C3'])
            self.assertEqual(row['description'], 'KT-Kondensator 100/10/630')
            self.assertEqual(row['article'], '0.7745 3400.0/90')

    def test_raw_multiline_table_is_preferred_over_broken_csv(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            inventory = json.loads(inventory_audit.INVENTORY.read_text())
            (root / 'page_007.alt.csv').write_text('broken,output\n')
            (root / 'page_007.alt.raw.txt').write_text(
                '<<<TABLE name="parts">>>\n'
                'Kurzzeichen;Stückzahl;Benennung;Sachnummer\n'
                '"R1, R3, R29";3;"Schichtwiderstand\n'
                '2,7 kOhm 5 %";"0.7121 3400.0/90"\n'
                '<<<END>>>\n')
            report = inventory_audit.audit(inventory, root)
            point = next(e for e in report['entries'] if e['id'] == '012-6921:R1')
            self.assertIn('alt', point['readings'])
            self.assertIn('2,7 kOhm', point['readings']['alt']['description'])

    def test_secondary_stock_cross_reference_can_be_a_separate_column(self):
        self.assertEqual(inventory_audit._primary_article(
            '0.7470 0808.0/90 005-0-509-861'), '0.7470 0808.0/90')
        self.assertEqual(inventory_audit._primary_article('0.7470 0808.0/90'),
                         '0.7470 0808.0/90')

    def test_three_full_page_passes_can_confirm_a_printed_blank_article(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            inventory = json.loads(inventory_audit.INVENTORY.read_text())
            for tag in ('', '.r300', '.alt'):
                (root / f'page_006{tag}.csv').write_text(
                    'Kurzzeichen,Stückzahl,Benennung,Sachnummer\n'
                    'C30,1,MKP-Kondensator 1000/10/1500,\n')
            report = inventory_audit.audit(inventory, root)
            point = next(e for e in report['entries'] if e['id'] == '012-6921:C30')
            self.assertEqual(point['blank_article_agreement_passes'],
                             ['primary', 'r300', 'alt'])
            self.assertEqual(point['status'], 'confirmed-by-3-passes')

    def test_malformed_article_is_not_a_blank_vote(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            inventory = json.loads(inventory_audit.INVENTORY.read_text())
            for tag in ('', '.r300', '.alt'):
                (root / f'page_014{tag}.csv').write_text(
                    'Kurzzeichen,Stückzahl,Benennung,Sachnummer\n'
                    'R26,1,Schichtwiderstand SWF 130 Ohm 2 %,077862 3535.0/90\n')
            report = inventory_audit.audit(inventory, root)
            point = next(e for e in report['entries'] if e['id'] == '012-6931:R26')
            self.assertTrue(point['article_format_suspect'])
            self.assertEqual(point['blank_article_agreement_passes'], [])
            self.assertEqual(point['status'], 'needs-source-review')

    def test_agreed_wrong_value_stays_for_review(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            inventory = json.loads(inventory_audit.INVENTORY.read_text())
            for tag in ('', '.r300', '.alt'):
                (root / f'page_006{tag}.csv').write_text(
                    'Kurzzeichen,Stückzahl,Benennung,Sachnummer\n'
                    'C1,1,KT-Kondensator 220/10/630,0.7745 3400.0/90\n')
            report = inventory_audit.audit(inventory, root)
            point = next(e for e in report['entries'] if e['id'] == '012-6921:C1')
            self.assertFalse(point['inventory_value_or_type_matches'])
            self.assertEqual(point['status'], 'needs-inventory-comparison')

    def test_resistor_match_requires_the_printed_ohms(self):
        part = next(p for p in json.loads(inventory_audit.INVENTORY.read_text())['parts']
                    if p['id'] == '012-6931:R30')
        reading = {'description': 'Schichtwiderstand SWF 100 Ohm 5 %', 'article': None}
        self.assertTrue(inventory_audit._printed_value_matches(part, reading))
        reading['description'] = 'Schichtwiderstand SWF 10 Ohm 5 %'
        self.assertFalse(inventory_audit._printed_value_matches(part, reading))

    def test_conflicting_printed_designator_requires_source_review_despite_votes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            inventory = json.loads(inventory_audit.INVENTORY.read_text())
            for tag in ('', '.r300', '.alt'):
                (root / f'page_015{tag}.csv').write_text(
                    'Kurzzeichen,Stückzahl,Benennung,Sachnummer\n'
                    '"V13, V26",2,Transistor KFY 18,0.7838 4452.0/90\n')
            report = inventory_audit.audit(inventory, root)
            point = next(e for e in report['entries'] if e['id'] == '012-6931:V13')
            self.assertTrue(point['inventory_value_or_type_matches'])
            self.assertEqual(len(point['description_agreement_passes']), 3)
            self.assertEqual(point['status'], 'needs-source-review')
            self.assertIn('diode group', point['source_conflict'])
            converter = next(e for e in report['entries'] if e['id'] == '012-6931:V22')
            self.assertEqual(converter['status'], 'needs-schematic-review')
            self.assertIn('V19 through V25', converter['source_conflict'])


if __name__ == '__main__':
    unittest.main()
