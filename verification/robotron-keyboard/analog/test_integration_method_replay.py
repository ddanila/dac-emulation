import unittest
from pathlib import Path
from integration_method_replay import prepare, refine_step


class IntegrationMethodTests(unittest.TestCase):
    def setUp(self):
        self.deck = (Path(__file__).parent/'reports/host-mpfr-transient/off/io.cir').read_text()

    def test_original_and_only_declared_option_changes(self):
        self.assertEqual(prepare(self.deck, 'original')[0], self.deck)
        for method, option in [('gear','.options method=gear maxord=2'),
                               ('trap1','.options method=trap maxord=1')]:
            with self.subTest(method=method):
                changed, receipt = prepare(self.deck,method)
                self.assertEqual(receipt['addedOptions'],option)
                self.assertEqual(changed.replace(option+'\n','',1).replace('\noption\n','\n',1),self.deck)
                self.assertLess(changed.index(option),changed.index('.control'))

    def test_timestep_preserves_stimulus_stop_and_tolerances(self):
        self.assertEqual(refine_step(self.deck,1)[0],self.deck)
        for divisor,token in [(2,'25.0n'),(4,'12.5n')]:
            changed,receipt=refine_step(self.deck,divisor)
            self.assertEqual(changed.replace('.tran '+token,'.tran 50.0n'),self.deck)
            self.assertEqual(receipt['stepNs'],50/divisor)
            self.assertAlmostEqual(receipt['derivedMinimumStepSeconds']/(50e-20/divisor),1)
        for altered in [self.deck.replace('50.0n','25n'),
                        self.deck.replace('.tran 50.0n','.tran 50.0n 0'),
                        self.deck+'\n.tran 50n .1\n']:
            with self.assertRaises(ValueError):refine_step(altered,2)

    def test_competing_or_hidden_configuration_rejected(self):
        for extra in ['.options METHOD=trap\n', '+ maxord=1\n',
                      '.include model.cir\n', 'set method=gear\n', 'option reltol=1\n']:
            with self.subTest(extra=extra):
                with self.assertRaises(ValueError):prepare(extra+self.deck,'gear')
        with self.assertRaises(ValueError):prepare(self.deck.replace('.control\n',''),'gear')
        with self.assertRaises(ValueError):prepare(self.deck,'unknown')


if __name__ == '__main__':unittest.main()
