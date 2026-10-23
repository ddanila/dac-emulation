#!/usr/bin/env python3
"""Summarize matched boundary controls without promoting numerical gains to qualification."""
import argparse,json
from pathlib import Path
from analog_driver_replay import sha

def review(root):
 baseline=json.loads((root/'zero-series.json').read_text())
 candidate=json.loads((root/'adc-series.json').read_text())
 if not baseline['completed'] or not candidate['completed']:raise ValueError('Incomplete refinement series')
 for level in (25,12,6):
  a=json.loads((root/f'network-zero{level}'/'run.json').read_text())
  b=json.loads((root/f'network-adc{level}'/'run.json').read_text())
  for key in ('inputs','sourceDeckSha256','deckSha256','stepNs','toleranceScale','fixtureCrossingGuardPs','mpfrStartNs','mpfrTransitionBits','method','enabled','conservativeCap','passiveAssembly'):
   if a[key]!=b[key]:raise ValueError('Candidate changed '+key)
  if a.get('adcCrossings',False) or not b['adcCrossings']:raise ValueError('Invalid ADC control modes')
  if a['runtime']['executable']!=b['runtime']['executable']:raise ValueError('Changed linear solver runtime')
  aa=a['runtime']['codeModels'];bb=b['runtime']['codeModels']
  if len(aa)!=len(bb):raise ValueError('Changed model set')
  for old,new in zip(aa,bb):
   if old!=new and not (old['path'].endswith('/digital.cm') and new['path'].endswith('/digital.cm')):raise ValueError('Changed unrelated model')
 controls=json.loads((root/'adc-disabled25/control.json').read_text())
 if not controls['disabledWaveformsUnchanged']:raise ValueError('Disabled correction changed witness')
 comparisons=[]
 for a,b in zip(baseline['pairs'],candidate['pairs']):
  if not all(p['firmwareDataMatches'] and p['firmwareLatchesMatch'] for p in (a,b)):raise ValueError('Firmware refinement mismatch')
  cross=[x['samples']==y['samples'] for x,y in zip(a['events'],b['events'])]
  if not all(cross):raise ValueError('Correction changed firmware read sequence')
  comparisons.append({'rmsReductionFactors':{name:old['rmsDifference']/b['signals'][name]['rmsDifference'] if b['signals'][name]['rmsDifference'] else None for name,old in a['signals'].items()},
   'candidatePeaks':{name:{'value':s['maximumAbsoluteDifference'],'unit':s['unit'],'timeSeconds':s['timeSeconds']} for name,s in b['signals'].items()},
   'candidateMaximumFirmwareEdgeDifferencePs':b['maximumFirmwareEdgeDifferencePs'],'firmwareReadsPreserved':all(cross)})
 evidence=('zero-series.json','adc-series.json','adc-disabled25/control.json','boundary-review.json','adc-crossing/assessment.json','adc-crossing-rc/assessment.json','unknown-output/assessment.json','traffic/assessment.json')
 return {'completedRefinementSeries':True,'qualified':False,'comparisons':comparisons,
 'evidenceSha256':{n:sha(root/n) for n in evidence},
 'remaining':['Absolute-time ideal-switch voltage peaks remain; no convergence waiver or phase alignment.',
 'Undefined receiver logic maps to a history-dependent ideal switch, not an admitted physical driver.',
 'Representative traffic is prepared and exercised in production C, but not executed electrically.'],
 'boundary':'Matched circuit, stimuli, precision policy and native solver at all three levels. Only the opt-in ADC model changes between series. RMS reductions are measured improvements, not physical accuracy guarantees.'}
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('root',type=Path);p.add_argument('--out',type=Path,required=True);a=p.parse_args();a.out.write_text(json.dumps(review(a.root),indent=2)+'\n')
