"""Column loads must use the canonical connector nets and remain explicit assumptions."""
import math
import unittest
from circuit import load, node
from matrix import matrix_circuit


class ColumnLoadTest(unittest.TestCase):
    def test_loads_cover_connector_columns_without_changing_contacts(self):
        components, _ = load()
        baseline, base_info = matrix_circuit(components)
        loaded, info = matrix_circuit(components, column_load_pf=1)
        capacitors = [line.split() for line in loaded if line.startswith('Ccolumn_load')]
        expected_nets = {node(net) for net in components['X1']['pins'].values()
                         if net and net.startswith('/COL')}
        self.assertEqual({parts[1] for parts in capacitors}, expected_nets)
        self.assertEqual(len(capacitors), len(expected_nets))
        self.assertTrue(all(parts[2:] == ['0', '1p'] for parts in capacitors))
        self.assertEqual([line for line in loaded if not line.startswith('Ccolumn_load')], baseline)
        self.assertEqual(info['contacts'], base_info['contacts'])
        self.assertEqual(info['columnLoadPf'], 1)
        self.assertEqual(base_info['columnLoadPf'], 0)

    def test_reported_capacitance_survives_deck_serialization(self):
        components, _ = load()
        lines, info = matrix_circuit(components, column_load_pf=1.2345678901234567)
        values = [float(line.split()[-1][:-1]) for line in lines if line.startswith('Ccolumn_load')]
        self.assertTrue(values)
        self.assertTrue(all(value == info['columnLoadPf'] for value in values))

    def test_invalid_capacitance_rejected(self):
        components, _ = load()
        for value in (-1, math.nan, math.inf, -math.inf):
            with self.subTest(value=value), self.assertRaises(ValueError):
                matrix_circuit(components, column_load_pf=value)


if __name__ == '__main__':
    unittest.main()
