"""Keep independent-solver replay explicit and reject incomplete evidence."""
import unittest
from xyce_transfer_fixture import OPTIONS, deck, rows, check_log


class XyceTransferTests(unittest.TestCase):
    def test_temperature_mapping(self):
        source = 'title\n.temp 25\n' + OPTIONS + '\nVcc vp 0 5\n.control\ndc Vin 0 1.6 .001\n.endc\n.end\n'
        result = deck(source)
        self.assertIn('.options device temp=25 tnom=27 gmin=1e-15', result)
        self.assertNotIn('.temp ', result)
        self.assertIn('Vcc vp 0 5', result)
        self.assertIn('.dc Vin 0 1.6 .001', result)
        for bad in [source.replace('.temp 25', '.temp 27'), source.replace(OPTIONS, '.options reltol=1e-3')]:
            with self.assertRaises(ValueError): deck(bad)

    def test_requires_complete_grid_and_footer(self):
        text = 'V(A) V(Y) I(VIN)\n' + '\n'.join(f'{i/1000:.4f} 1 0' for i in range(1601)) + '\nEnd of Xyce(TM) Simulation'
        self.assertEqual(len(rows(text, .001, False)), 1601)
        for bad in [text.replace('End of Xyce(TM) Simulation', ''), text + '\nextra',
                    text.replace('0.1000 1', '0.0990 1'), text.replace('0.1000 1', '0.1000 nan')]:
            with self.assertRaises(ValueError): rows(bad, .001, False)

    def test_rejects_ignored_directives_and_solver_failures(self):
        clean = '\n'.join(label + ': 0' for label in ['Number Failed Steps Attempted',
            'Number Failed Linear Solves', 'Number Nonlinear Convergence Failures'])
        check_log(clean)
        for bad in [clean + '\nNetlist warning: Unrecognized dot line', clean.replace(': 0', ': 1', 1), '']:
            with self.assertRaises(ValueError): check_log(bad)


if __name__ == '__main__': unittest.main()
