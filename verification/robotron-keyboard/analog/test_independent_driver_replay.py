import unittest
from independent_driver_replay import convert

FIXTURE = '''S600 replay
.model CONTACT_NOMINAL SW(RON=100 ROFF=1t VT=2.5 VH=0)
Scontact0 a b control 0 CONTACT_NOMINAL
Vcontrol control 0 PWL(0 0 1n 5)
Rload a 0 560
Btarget y 0 V=V(a)*.7
.options reltol=0.0001 vntol=1e-07 abstol=1e-13
.options trtol=1
.tran 50n .001
.control
wrdata host-trace.txt v(a) v(b)
quit
.endc
.end
'''


class ConversionTests(unittest.TestCase):
    def test_both_solvers_keep_circuit_and_stimulus(self):
        for engine in ['ngspice','xyce']:
            deck,changes,signals,stop=convert(FIXTURE,engine)
            self.assertIn('Vcontrol control 0 PWL(0 0 1n 5)',deck)
            self.assertIn('Rload a 0 560',deck)
            self.assertIn('Btarget y 0 V={V(a)*.7}',deck)
            self.assertIn('I={V(a,b)/(V(control,0)>2.5 ? 100 : 1t)}',deck)
            self.assertNotIn(' SW(',deck)
            self.assertEqual(changes[0]['original'],'Scontact0 a b control 0 CONTACT_NOMINAL')
            self.assertEqual(signals,['v(a)','v(b)'])
            self.assertEqual(stop,.001)

    def test_unknown_switch_and_live_interface_rejected(self):
        for text in [FIXTURE.replace('RON=100','RON=50'),
                     FIXTURE.replace('Scontact0 a b control 0 CONTACT_NOMINAL','Scontact0 a b control 0 other'),
                     FIXTURE.replace('Rload a 0 560','Ahdl [a] [b] hdl')]:
            with self.assertRaises(ValueError): convert(text,'xyce')

    def test_implicit_truncation_tolerance_rejected(self):
        with self.assertRaises(ValueError):
            convert(FIXTURE.replace('.options trtol=1\n',''),'ngspice')

    def test_missing_capture_rejected(self):
        with self.assertRaises(ValueError):
            convert(FIXTURE.replace('wrdata host-trace.txt','wrdata other.txt'),'xyce')
