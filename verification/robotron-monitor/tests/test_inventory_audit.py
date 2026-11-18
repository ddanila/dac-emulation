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

    def test_machine_agreement_still_requires_inventory_comparison(self):
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
            self.assertEqual(point['status'], 'needs-inventory-comparison')
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


if __name__ == '__main__':
    unittest.main()
