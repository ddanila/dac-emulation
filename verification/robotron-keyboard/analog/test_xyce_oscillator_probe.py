"""Check solver-adapter wiring, expression syntax and waveform completeness."""
from pathlib import Path
import tempfile
import unittest

from circuit import load
from xyce_oscillator_probe import deck, model_for_xyce, normalize


class AdapterTests(unittest.TestCase):
    def test_supply_is_on_package_supply_not_bridge_source(self):
        components, _ = load()
        text = deck(components, .25)
        self.assertIn('Vcc n_p5V 0 PWL(0 0 10n 5)', text)
        self.assertNotIn('Vcc n_OSC_OUT', text)
        self.assertIn('RBR1 n_OSC_OUT n_CLK .001', text)
        self.assertIn('.tran 0.25n 2.0000000000000002e-05 0 0.25n', text)
        recorded = deck(components, .25, .00025, True)
        self.assertIn('Bsupply n_p5V 0 V={fasttable("../supply.txt")}', recorded)
        self.assertNotIn('PWL(0 0 10n 5)', recorded)
        self.assertIn('V(n_CLK) V(n_p5V)', recorded)
        pwl = deck(components, .25, .00025, True, 'pwl')
        self.assertIn('Vcc n_p5V 0 PWL FILE "../supply.txt"', pwl)
        self.assertNotIn('fasttable', pwl)
        self.assertIn('RBR1 n_OSC_OUT n_CLK .001', pwl)
        with self.assertRaises(ValueError):
            deck(components, .25, .00025, True, 'unknown')

    def test_only_behavioral_expression_delimiters_change(self):
        source = (Path(__file__).parent / 'ls_nand_pullup.cir').read_text()
        converted = model_for_xyce(source)
        self.assertEqual(converted.replace('{', '').replace('}', ''),
                         source.replace('{', '').replace('}', ''))
        self.assertIn('I={V(y,g)*(1-V(filtered,g))/rout}', converted)
        with self.assertRaises(ValueError):
            model_for_xyce(source.replace('Btarget', 'Xtarget'))

    def test_recorded_supply_column_survives_normalization(self):
        from oscillator_supply_replay import check_supply
        with tempfile.TemporaryDirectory() as directory:
            source, target = Path(directory) / 'source', Path(directory) / 'target'
            source.write_text('TIME V(N_CLK) V(N_P5V)\n0 0 0\n0.000125 2 2.5\n0.00025 3 5\nEnd of Xyce(TM) Simulation\n')
            normalize(source, target, .00025, True)
            result = check_supply(target, [0, .00025], [0, 5])
            self.assertEqual(result['maximumInterpolationErrorVolts'], 0)
            with self.assertRaises(ValueError):
                normalize(source, target)

    def test_numeric_tokens_preserved_and_incomplete_output_rejected(self):
        valid = 'TIME V(N_CLK)\n0.00000000000000000e+00 0\n1.99999999999999982e-05 5\nEnd of Xyce(TM) Simulation\n'
        with tempfile.TemporaryDirectory() as directory:
            source, target = Path(directory) / 'source', Path(directory) / 'target'
            source.write_text(valid)
            self.assertEqual(normalize(source, target), 2)
            self.assertIn('1.99999999999999982e-05 5', target.read_text())
            for bad in [valid.replace('End of Xyce(TM) Simulation\n', ''),
                        valid.replace('1.99999999999999982e-05', '1e-5'),
                        valid.replace(' 5\n', ' nan\n'), valid + '1 2\n']:
                source.write_text(bad)
                with self.assertRaises(ValueError):
                    normalize(source, target)


if __name__ == '__main__':
    unittest.main()
