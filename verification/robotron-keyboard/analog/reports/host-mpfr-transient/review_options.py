#!/usr/bin/env python3
"""Recheck a retained options-heading false positive without replacing its producer report."""
import argparse
import json
from pathlib import Path
import sys

ANALOG=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ANALOG))
from analog_driver_replay import sha
from failure_evidence import solver_diagnostic

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('run',type=Path)
parser.add_argument('--out',type=Path,required=True)
args=parser.parse_args()
p=args.run/'report.json';parent=json.loads(p.read_text())
if (parent.get('error') or parent['solverDiagnostic'] != 'Truncation error correction, charge based, is selected:' or
    not parent.get('effectiveIntegrationVerified') or parent['precisionGuardDiagnostics']):
    raise ValueError('Not the admitted options-heading false positive')
for name,digest in parent['artifacts'].items():
    if sha(args.run/name)!=digest:raise ValueError('Changed input '+name)
text=(args.run/'ngspice.log').read_text()
prefixes=('TRUNC_AUDIT ','TRANSITION_AUDIT ','NODE_AUDIT ','INDUCTOR_AUDIT ','LINEAR_AUDIT ')
messages='\n'.join(line for line in text.splitlines() if not line.startswith(prefixes))
diagnostic=solver_diagnostic(messages)
complete=(parent['exitCode']==0 and diagnostic is None and len(parent['waveforms'])==4 and
          all(v['rows']>0 and abs(v['lastSampleSeconds']-parent['stopSeconds'])<1e-15
              for v in parent['waveforms'].values()))
report={'qualified':False,'completed':complete,'scope':__doc__,
        'sourceReportSha256':sha(p),'artifactsVerified':parent['artifacts'],
        'sources':{'review_options.py':sha(__file__),'failure_evidence.py':sha(ANALOG/'failure_evidence.py')},
        'solverDiagnostic':diagnostic,'waveforms':parent['waveforms'],
        'interpretation':'Original report is preserved. Its waveform parser accepted every row and reached the declared endpoint. Hash-verified outputs and log are unchanged; only the exact informational options heading is excluded from diagnostic scanning. Completion does not establish convergence or circuit qualification.'}
args.out.write_text(json.dumps(report,indent=2)+'\n')
print(args.out)
if not complete:raise SystemExit(1)
