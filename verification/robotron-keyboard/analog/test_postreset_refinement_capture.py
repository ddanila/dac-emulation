from pathlib import Path
import unittest
from postreset_refinement_capture import refined_deck, ORIGINAL_TRAN, STEPS

HERE=Path(__file__).resolve().parent


class RefinementCaptureTests(unittest.TestCase):
    def test_only_timestep_changes_in_real_completed_fixture(self):
        deck=(HERE/'reports/postreset-startup-fixes/combined/io.cir').read_text()
        for step in STEPS:
            result=refined_deck(deck,step)
            replacement=f'\n.tran {step:g}n 1.16e+06n\n'
            self.assertEqual(result.replace(replacement,ORIGINAL_TRAN),deck)
            self.assertEqual(result.count('1000000n 0 1000001n 5'),1)
            self.assertIn('.options trtol=0.25',result)

    def test_shortened_moved_or_ambiguous_stimulus_is_rejected(self):
        deck=(HERE/'reports/postreset-startup-fixes/combined/io.cir').read_text()
        for bad in (deck.replace('1.16e+06n','1.1e+06n'),
                    deck.replace('1000000n 0 1000001n 5','1n 0 2n 5'),
                    deck+'\n.tran 1n 10n\n',deck.replace('.tran 25n','.tran 12.5n')):
            with self.assertRaises(ValueError):refined_deck(bad,12.5)
        for step in (0,25,10,float('nan'),float('inf')):
            with self.assertRaises(ValueError):refined_deck(deck,step)


if __name__=='__main__':unittest.main()
