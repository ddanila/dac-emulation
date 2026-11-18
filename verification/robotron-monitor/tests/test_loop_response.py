from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import loop_response as loop

class LoopTests(unittest.TestCase):
    def test_phase_translation_preserves_knots_and_cycle_integral(self):
        for phase in (0,.123,-.123,.999):
            text=loop.wave([0,4,0,0],1,phase)
            numbers=list(map(float,text.removeprefix('PWL(').split(')')[0].split()))
            knots=list(zip(numbers[::2],numbers[1::2]))
            self.assertEqual(knots[0][0],0);self.assertEqual(knots[-1][0],1)
            self.assertEqual(max(v for t,v in knots),4)
            self.assertAlmostEqual(sum((b-a)*(u+v)/2 for (a,u),(b,v) in zip(knots,knots[1:])),1)
            self.assertTrue(any(abs(t-((.25+phase)%1))<1e-12 and v==4 for t,v in knots))

    def test_negative_correction_requires_refined_sign(self):
        self.assertTrue(loop.correction(-2,.1)['corrective'])
        self.assertFalse(loop.correction(2,.1)['corrective'])
        self.assertFalse(loop.correction(2,.1)['connected_lock_verified'])
        self.assertTrue(loop.refined_sign(1,1.005)['verified'])
        self.assertFalse(loop.refined_sign(1,1.04)['verified'])
        self.assertFalse(loop.refined_sign(1,-1)['verified'])
        self.assertFalse(loop.refined_sign(0,0)['verified'])

    def test_pulse_response_requires_identical_pre_pulse_history(self):
        period=62.5e-6;times=[.003+i*period for i in range(30)]
        base=dict(edges_s=times)
        plus=dict(edges_s=[v+(.000001 if v>.0035625 else 0) for v in times])
        minus=dict(edges_s=[v-(.000001 if v>.0035625 else 0) for v in times])
        self.assertAlmostEqual(loop.pulse_response(base,minus,plus,period,.05),.32,places=10)
        plus['edges_s'][0]+=1e-6
        with self.assertRaisesRegex(ValueError,'pre-pulse'):loop.pulse_response(base,minus,plus,period,.05)

if __name__=='__main__':unittest.main()
