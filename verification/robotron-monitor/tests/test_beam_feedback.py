import copy,json,sys,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import beam_feedback as feedback
import collection


def load(charge=1e-9):
    c=collection.PeriodicCollector(.02,bins=4)
    for i in range(4):c.add(i*.005,i*.005,charge/4,charge*10000/4,'anode','phosphor')
    return c.report(charge)


class FeedbackTests(unittest.TestCase):
    def test_relaxation_conserves_charge_without_claiming_measured_energy(self):
        a,b=load(),load(2e-9);r=feedback.relax(a,b,.5)
        self.assertAlmostEqual(r['emitted_charge_c'],1.5e-9)
        self.assertAlmostEqual(feedback.residual(a,b),.5)
        self.assertNotIn('trajectory_electric_work_j',r)
        for alpha in (0,-1,2,float('nan')):
            with self.assertRaises(ValueError):feedback.relax(a,b,alpha)

    def exercise(self,root,*,locked=True,collect=None,iterations=3):
        metadata=dict(period_s=.02,simulated_fields=4,yoke={'field':{}})
        def solve(text,folder,*args,**kwargs):
            folder.mkdir();return {'status':'complete'}
        with patch.object(feedback.steady_trace,'export',return_value={'current_definition':'post-grid2-launch'}), \
             patch.object(feedback,'collect',side_effect=collect or (lambda *a,**k:load())), \
             patch.object(feedback.steady_supply,'deck',return_value=('deck',metadata)), \
             patch.object(feedback.electrical_cache,'solve',side_effect=solve), \
             patch.object(feedback.steady_supply,'assess',side_effect=[{'accepted':True}]+[{'accepted':locked}]*iterations), \
             patch.object(feedback.steady_acceptance,'compare',return_value={'accepted':True}):
            return feedback.run({}, {}, {}, metadata,root/'base',root/'feedback','runtime',{},time.monotonic()+10,max_iterations=iterations)

    def test_two_consecutive_passes_and_lock_are_both_required(self):
        for locked in (True,False):
            with tempfile.TemporaryDirectory() as tmp:
                r=self.exercise(Path(tmp),locked=locked)
                self.assertTrue(r['converged']);self.assertEqual(r['accepted'],locked)
                self.assertEqual(len(r['iterations']),2)
                self.assertFalse(r['full_monitor_qualified'])

    def test_divergent_load_cannot_pass(self):
        count=0
        def diverge(*args,**kwargs):
            nonlocal count
            count+=1;return load(1e-9*2**count)
        with tempfile.TemporaryDirectory() as tmp:
            r=self.exercise(Path(tmp),collect=diverge)
            self.assertFalse(r['accepted']);self.assertFalse(r['converged'])
            self.assertIn('budget',r['reason']);self.assertIn('latest_completed',r)

    def test_failed_collection_retains_latest_completed_solve(self):
        count=0
        def fail(*args,**kwargs):
            nonlocal count
            count+=1
            if count>1:raise ValueError('unsupported collector')
            return load()
        with tempfile.TemporaryDirectory() as tmp:
            r=self.exercise(Path(tmp),collect=fail)
            self.assertFalse(r['accepted']);self.assertIn('iteration-00',r['latest_completed']['trial'])

    def test_expired_budget_does_not_start_work(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(feedback.steady_trace,'export') as export:
            r=feedback.run({}, {}, {}, {},'missing',Path(tmp)/'feedback','runtime',{},time.monotonic()-1)
            export.assert_not_called();self.assertFalse(r['accepted'])

    def test_unlocked_input_does_not_start_collection_or_solve(self):
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(feedback.steady_supply,'assess',return_value={'accepted':False}), \
             patch.object(feedback.steady_trace,'export') as export:
            r=feedback.run({}, {}, {}, {},'missing',Path(tmp)/'feedback','runtime',{},time.monotonic()+10)
            export.assert_not_called();self.assertFalse(r['accepted'])
            self.assertIn('synchronized',r['reason'])

if __name__=='__main__':unittest.main()
