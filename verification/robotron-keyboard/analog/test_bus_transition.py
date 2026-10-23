import tempfile,unittest
from pathlib import Path
from bus_transition_probe import dac_nodes,replay,settings,compress_boundary
from bus_transition_review import extent,stop_time
class TransitionTests(unittest.TestCase):
 def test_replay_preserves_analog_feedback_network(self):
  deck='test\nVhost p 0 5\nCrail p 0 47u\nBload p d I=V(d)\nAdrive [din] [intent] drive\n.model drive dac_bridge(out_high=5)\n.tran 25n 1160000n\n.control\n.endc\n.end'
  self.assertEqual(dac_nodes(deck),['intent'])
  isolated=replay(deck,['intent'],[[(0,0),(1e-6,5)]])
  for line in ('Vhost p 0 5','Crail p 0 47u','Bload p d I=V(d)'):self.assertIn(line,isolated)
  self.assertNotIn('Adrive',isolated);self.assertNotIn('dac_bridge',isolated);self.assertIn('Vreplay_intent',isolated)
  self.assertEqual(stop_time(settings(deck,'tight')),stop_time(deck))
 def test_plateau_compression_keeps_ramp_knots(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp)/'trace';p.write_text('time v(intent)\n0 0\n1 0\n2 0\n3 1\n4 2\n5 2\n6 2\n')
   self.assertEqual(compress_boundary(p,['intent']),[[(0,0),(2,0),(3,1),(4,2),(6,2)]])
   self.assertEqual(extent(p)['lastSeconds'],6)
   p.write_text('time v(intent)\n0 0\n1 nan\n')
   with self.assertRaises(ValueError):extent(p)
if __name__=='__main__':unittest.main()
