import unittest
from pathlib import Path
from integration_method_replay import prepare


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

    def test_competing_or_hidden_configuration_rejected(self):
        for extra in ['.options METHOD=trap\n', '+ maxord=1\n',
                      '.include model.cir\n', 'set method=gear\n', 'option reltol=1\n']:
            with self.subTest(extra=extra):
                with self.assertRaises(ValueError):prepare(extra+self.deck,'gear')
        with self.assertRaises(ValueError):prepare(self.deck.replace('.control\n',''),'gear')
        with self.assertRaises(ValueError):prepare(self.deck,'unknown')


if __name__ == '__main__':unittest.main()
