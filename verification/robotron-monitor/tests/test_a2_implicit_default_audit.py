"""Check that the A2 default screen covers the registered frame path."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import a2_implicit_default_audit as audit


class A2ImplicitDefaultAuditTests(unittest.TestCase):
    def test_registered_semiconductor_coverage_and_multiline_parse(self):
        saved = json.loads((ROOT/'reference/k7222-11/a2-implicit-default-audit.json').read_text())
        live = audit.run()
        self.assertEqual(saved, live)
        coverage = json.loads((ROOT/'reference/k7222-11/device-model-coverage.json').read_text())
        expected = {row['id'] for row in coverage['devices']
                    if row['kind'] in ('bjt', 'diode', 'zener')}
        actual = [member for row in live['rows'] for member in row['member_ids']]
        self.assertEqual(set(actual), expected)
        self.assertEqual(len(actual), len(expected))
        self.assertEqual(live['affected_instances'], sum(
            len(row['member_ids']) for row in live['rows']
            if row['critical_implicit_defaults']))
        self.assertEqual(live['affected_instances'], 0)
        v10 = next(row for row in live['rows'] if row['id'] == '012-6921:V10')
        self.assertEqual(v10['critical_implicit_defaults'], [])
        self.assertEqual(v10['explicit_keys_without_same_named_register_field'], [])
        with tempfile.TemporaryDirectory() as tmp:
            model = Path(tmp)/'models.cir'
            model.write_text('.model X D(IS=1n N=1.5\n+ RS=2 TT=5n)\n')
            self.assertEqual(audit.declaration(model, 'X'),
                             ('D', {'IS', 'N', 'RS', 'TT'}))


if __name__ == '__main__':
    unittest.main()
