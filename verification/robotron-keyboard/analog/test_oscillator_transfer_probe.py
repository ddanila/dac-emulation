"""Check equilibrium bookkeeping independently of a particular SPICE model."""
import unittest
from oscillator_transfer_probe import equilibria,direction_difference


class EquilibriumTests(unittest.TestCase):
    def test_exact_grid_root_is_not_lost_or_counted_twice(self):
        rows=[[0,3,0,5,-1],[1,2,2,4,0],[2,1,4,3,1]]
        roots=equilibria(rows)
        self.assertEqual(len(roots),1)
        self.assertEqual(roots[0]['interpolatedVolts']['oscRc'],1)
        self.assertEqual(roots[0]['localSlopes']['osc2VsOsc1'],-2)

    def test_multiple_equilibria_and_ambiguous_plateau(self):
        rows=[[0,3,0,5,-1],[1,2,1,4,1],[2,1,2,3,-1]]
        self.assertEqual([r['interpolatedVolts']['oscRc'] for r in equilibria(rows)],[.5,1.5])
        with self.assertRaisesRegex(ValueError,'Ambiguous'):
            equilibria([[0,3,0,5,0],[1,2,1,4,0]])

    def test_reverse_sweep_and_branch_difference(self):
        rows=[[i,3-i,2*i,i,i-1]for i in range(4)]
        reverse=list(reversed(rows))
        self.assertEqual(equilibria(rows)[0]['interpolatedVolts'],equilibria(reverse)[0]['interpolatedVolts'])
        self.assertEqual(direction_difference(rows,reverse,1)['osc2']['maximumDifferenceVolts'],0)
        changed=[r[:]for r in reverse];changed[1][2]+=2
        self.assertEqual(direction_difference(rows,changed,1)['osc2']['maximumDifferenceVolts'],2)

    def test_no_root_is_not_a_stability_claim(self):
        self.assertEqual(equilibria([[0,3,0,5,1],[1,2,1,4,2]]),[])


if __name__=='__main__':unittest.main()
