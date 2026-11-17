"""Check the passive AC-loss network against its analytic complex impedance."""
import math
from pathlib import Path
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import lab
import magnetics


class WindingLossTests(unittest.TestCase):
    def test_low_frequency_leakage_and_high_frequency_copper_loss(self):
        winding=dict(turns=10,resistance_ohm=.2,leakage_h=2e-6,
                     capacitance_f=1e-18,skin_resistance_ohm=10,skin_fraction=.9)
        lines=magnetics.winding_network(0,winding,'p','0')
        deck='Passive winding impedance\nItest 0 p AC 1\nVshort l0 0 0\n'+'\n'.join(lines)+'''
.control
set noaskquit
set wr_singlescale
set wr_vecnames
set numdgt=15
ac dec 4 1k 100meg
let zr=real(v(p))
let zi=imag(v(p))
wrdata samples.txt zr zi
quit
.endc
.end
'''
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp);(out/'run.cir').write_text(deck)
            lab.run_command(['ngspice','-b','run.cir'],out,out/'solver.log')
            rows=[list(map(float,line.split())) for line in (out/'samples.txt').read_text().splitlines()[1:]]
        self.assertGreater(len(rows),10)
        for f,real,imag in rows:
            jw=2j*math.pi*f
            branch=10*jw*1.8e-6/(10+jw*1.8e-6)
            series=.2+jw*.2e-6+branch
            expected=series/(1+jw*1e-18*series)
            actual=complex(real,imag)
            self.assertLess(abs(actual-expected)/abs(expected),1e-8)
            self.assertGreater(real,0) # dissipative at every sampled frequency
        self.assertAlmostEqual(rows[0][2]/(2*math.pi*rows[0][0]),2e-6,delta=2e-9)
        self.assertAlmostEqual(rows[-1][1],10.2,delta=.01)

    def test_loss_requires_both_valid_passive_parameters(self):
        core=dict(area_m2=1e-4,length_m=.05,loss_ohm=10000,
                  h_a_per_m=[-1000,0,1000],b_t=[-.2,0,.2])
        normal=dict(turns=20,resistance_ohm=.2,leakage_h=2e-6,capacitance_f=10e-12)
        for changes in ({'skin_fraction':.9},{'skin_resistance_ohm':10},
                        {'skin_resistance_ohm':-1,'skin_fraction':.9},
                        {'skin_resistance_ohm':10,'skin_fraction':1}):
            with self.assertRaises(ValueError):magnetics.transformer_flux('T',[normal,normal|changes],core)
        text=magnetics.transformer_flux('T',[normal,normal|dict(skin_resistance_ohm=10,skin_fraction=.9)],core)
        self.assertIn('Rskin1',text);self.assertNotIn('Rskin0',text)

if __name__=='__main__':unittest.main()
