#!/usr/bin/env python3
import re,unittest
from decimal import Decimal as D
from fixture_crossing_grid import add_crossings

DECK='''Vfixture_clock fixture_clock 0 PULSE(0 5 500n 1n 1n 499n 1u)
Vfixture_reset fixture_reset 0 PWL(0 0 1000000n 0 1000001n 5)
.model clock_receiver adc_bridge(in_low=1.4 in_high=1.4)
'''
class CrossingGridTest(unittest.TestCase):
 def test_threshold_and_guard_refinement(self):
  for guard in (1,.5,.25):
   result=add_crossings(DECK,guard)
   self.assertTrue(result.endswith(DECK))
   points=[D(t) for t in re.findall(r'^\+ ([0-9.]+)n 0$',result,re.M)]
   self.assertEqual(points,sorted(set(points)))
   for edge in (D('500.28'),D('1000.72'),D('1000000.28')):
    self.assertIn(edge+D(str(guard))/1000,points)
 def test_service_reset_crossings(self):
  from io_scenario import reset_source
  scenario={'cycles':30,'resets':[{'cycle':10,'asserted':True},{'cycle':26,'asserted':False}]}
  deck=DECK.replace('PWL(0 0 1000000n 0 1000001n 5)',reset_source(scenario))
  grid=add_crossings(deck,.25,scenario)
  self.assertIn('+ 1010000.72025n 0',grid)
  self.assertIn('+ 1026000.28025n 0',grid)
  bounded=add_crossings(deck,.25,scenario,stop_ns=1015000)
  self.assertIn('+ 1010000.72025n 0',bounded)
  self.assertNotIn('+ 1026000.28025n 0',bounded)
  with self.assertRaises(ValueError):add_crossings(DECK,.25,scenario)
 def test_bounded_grid_preserves_prefix(self):
  full=add_crossings(DECK,.25)
  for stop in (100, 500.28025, 1006000):
   bounded=add_crossings(DECK,.25,stop_ns=stop)
   points=lambda text: [D(t) for t in re.findall(r'^\+ ([0-9.]+)n 0$',text,re.M)]
   self.assertEqual(points(bounded),[t for t in points(full) if t<=D(str(stop))])
   self.assertTrue(bounded.endswith(DECK))
  scenario={'cycles':1600000,'resets':[]}
  self.assertEqual(add_crossings(DECK,.25,scenario,stop_ns=1006000),
                   add_crossings(DECK,.25,stop_ns=1006000))
  for stop in (0,-1,float('nan'),float('inf')):
   with self.assertRaises(ValueError):add_crossings(DECK,stop_ns=stop)
 def test_reject_unrecognized_physics(self):
  with self.assertRaises(ValueError):add_crossings(DECK.replace('1.4','1.5'))
  with self.assertRaises(ValueError):add_crossings(DECK,2)
if __name__=='__main__':unittest.main()
