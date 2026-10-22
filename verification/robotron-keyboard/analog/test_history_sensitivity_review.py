import math
import unittest
from fractions import Fraction as F
from history_sensitivity_review import sensitivity,selected_log

class HistoryTests(unittest.TestCase):
    def test_grounded_capacitor_matches_analytic_response(self):
        # Conductance 2 S; q1 RHS multiplier 4 /s. Half-ULP q error gives ULP volts.
        before={'name':'c','p':1,'n':0,'m':1.,'C':.5,'ag0':4.,'ag1':-1.,'q1':1.,'i1':0.,'geq':2.,'ceq':-4.,'pp':0.,'nn':0.,'pn':0.,'np':0.,'bp':0.,'bn':0.}
        after={'pp':2.,'nn':2.,'pn':-2.,'np':-2.,'bp':4.,'bn':-4.}
        group={'order':2,'capacitors':[{'before':before,'after':after}]}
        system={'id':1,'metadata':{'size':'1','time':float(1).hex(),'delta':float(.5).hex()},'a':{(1,1):F(2)},'b':{1:F(4)},'names':{0:'host_receiver_gnd',1:'n_cable_daten'}}
        r=sensitivity(system,group)
        self.assertAlmostEqual(r['independentHalfUlpHistoryBoundV'],math.ulp(1.),delta=1e-30)
        self.assertFalse(math.isnan(r['adjoint80Vs160Scaled']))
if __name__=='__main__':unittest.main()
