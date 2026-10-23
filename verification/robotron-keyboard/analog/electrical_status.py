#!/usr/bin/env python3
"""Index scoped electrical findings for DAC; individual qualifiers own acceptance."""
import argparse,json
from pathlib import Path
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent
EVIDENCE={
 'staticDeviceEndpoints':('reports/device-endpoints/assessment.json','staticEndpointsPassed'),
 'numericalConvergence':('reports/host-device-additions/assessment.json','qualified'),
 'bridgeTimeOrdering':('reports/input-barrier/assessment.json','orderingRegressionPassed'),
 'oscillatorDynamics':('reports/clock-output/device-admission/assessment.json','qualified'),
 'serialDriverDynamics':('reports/host-driver-switching/assessment.json','qualified'),
 'hostBufferDynamics':('reports/host-buffer-switching/assessment.json','qualified'),
 'closedBoardElectrical':('reports/input-barrier/assessment.json','qualified')}

def status():
 evidence={};gates={}
 for key,(name,field) in EVIDENCE.items():
  path=HERE/name;report=json.loads(path.read_text())
  if type(report[field]) is not bool or report.get('completed') is not True:raise ValueError('Incomplete evidence: '+name)
  gates[key]=report[field];evidence[key]={'path':name,'sha256':sha(path),'field':field}
 return {'qualified':all(gates.values()),'gates':gates,'evidence':evidence,
         'scope':'Current reference electrical evidence; separate from production digital acceptance. Static endpoint screens are not device-dynamics qualification. Bridge ordering covers the retained input-driven regression and matched service pair, not arbitrary HDL rollback. The qualified-CPU full-board startup attempt is incomplete.',
         'remainingAcceptance':['Resolve supply-relative bus voltage and numerical convergence','Admit oscillator and switching models against independent conditions','Complete matched coupled startup, keys/chords, repeat/release, reset and supply-recovery scenarios'],
         'generatorSha256':sha(Path(__file__))}

def main():
 p=argparse.ArgumentParser();p.add_argument('--check',action='store_true');a=p.parse_args();path=HERE/'reports/electrical-status.json';result=status()
 if a.check:
  if json.loads(path.read_text())!=result:raise ValueError('Stale electrical status')
 else:path.write_text(json.dumps(result,indent=2)+'\n')
 print('Electrical evidence index matches scoped source reports.')
if __name__=='__main__':main()
