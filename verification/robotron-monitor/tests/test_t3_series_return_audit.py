"""The series-return claim must depend on both external joins."""

import copy
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import t3_series_return_audit as audit


class T3SeriesReturnAuditTests(unittest.TestCase):
    def test_opening_either_join_removes_the_ground_path(self):
        graph = json.loads(audit.GRAPH.read_text())
        assembly = json.loads(audit.ASSEMBLY.read_text())
        _, path, _ = audit.candidate_path(graph, assembly)
        self.assertIn('NET:0', path)
        for port in ('X1_3', 'X2_5'):
            modified = copy.deepcopy(assembly)
            t3 = next(part for part in modified['components']
                      if part['source_id'] == '012-6921:T3')
            t3['nodes'][modified['ports'].index(port)] = 'disconnected_' + port
            _, opened, _ = audit.candidate_path(graph, modified)
            self.assertEqual(opened, [], port)


if __name__ == '__main__':
    unittest.main()
