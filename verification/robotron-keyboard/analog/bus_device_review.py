#!/usr/bin/env python3
"""Audit bus stress fixtures against source conditions without relaxing read limits."""
import argparse,json,math
from pathlib import Path
from bus_driver import wiring
from circuit import load
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent

from bus_input_limits import classify_input

def assess():
 limits=json.loads((HERE/'bus_limits.json').read_text());contract=json.loads((HERE/'bus_device_contract.json').read_text());components,_=load()
 _,model=wiring(components,limits,{'I8282':5,'7406':5});drivers=[]
 for driver in model['drivers']:
  profile=limits['profiles'][driver['profile']];conditions=contract['devices'][driver['profile']];lo,hi=conditions['supplyRangeVolts'];points=[]
  for supply in (lo,5,hi):
   high=supply-driver['highOhms']*profile['outputHigh']['sourceMagnitudeAmps'];low=driver['lowOhms']*profile['outputLow']['sinkAmps']
   points.append({'supplyVolts':supply,'predictedLoadedHighVolts':high,'predictedLoadedLowVolts':low,
                  'highDeficitVolts':max(0,profile['outputHigh']['minimumVolts']-high),
                  'endpointPassed':high>=profile['outputHigh']['minimumVolts']-1e-12 and low<=profile['outputLow']['maximumVolts']+1e-12})
  drivers.append(dict(driver,points=points,fullSupplyEndpointEnvelopePassed=all(p['endpointPassed'] for p in points),admitted=False,
                      unresolved=conditions['unresolved']))
 read=json.loads((HERE/'reports/bus-read-replay/assessment.json').read_text())['runs']['tighter']
 return {'qualified':False,'drivers':drivers,'observedRead':classify_input(read['volts'],read['supplyVolts'],True),
         'decision':'Keep linear drivers as explicitly unqualified stress fixtures. Nominal endpoint interpolation fails the published high-level load guarantee at minimum rated supply; it cannot identify a physical transient fault. Do not repair this by choosing arbitrary clamps, leakage or voltage tolerances.',
         'serviceAcceptance':'Still gated by unchanged static input range and coupled refinement/model admission.',
         'sources':{n:sha(HERE/n) for n in ('bus_device_review.py','bus_input_limits.py','bus_device_contract.json','bus_limits.json','cpu_clock_limits.json','bus_driver.py','bus_load.py','reports/bus-read-replay/assessment.json')},
         'arithmeticBoundary':'The 1e-12 V comparison allowance applies only to analytic floating-point endpoint arithmetic, never to captured input voltage acceptance.'}

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);p.add_argument('--verify',action='store_true');a=p.parse_args();report=assess()
 if a.verify:
  if report!=json.loads(a.out.read_text()):raise ValueError('Stale bus-device review')
  print('Bus-device review verified; model admission remains open.')
 else:a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(report,indent=2)+'\n')
if __name__=='__main__':main()
