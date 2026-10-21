#!/usr/bin/env python3
"""Retain explicitly truncated accepted-state captures; never qualification runs."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ANALOG = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ANALOG))
from accepted_capture_review import budget_stop
def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b''):
            digest.update(chunk)
    return digest.hexdigest()

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('source', type=Path)
p.add_argument('--runtime', type=Path, required=True)
p.add_argument('--build-provenance', type=Path, required=True)
p.add_argument('--mode', choices=('off', 'exact'), required=True)
p.add_argument('--step-divisor', type=int, choices=(1,2), default=1)
p.add_argument('--limit', type=int)
p.add_argument('--after', type=float)
p.add_argument('--out', type=Path, required=True)
p.add_argument('--review-existing', action='store_true')
a = p.parse_args()
if (a.limit is None) != (a.after is None):
    p.error('--limit and --after must be supplied together')
provenance = json.loads(a.build_provenance.read_text())
for key, name in [('budgetPatchSha256','ngspice-47-accepted-budget.patch'),
                  ('budgetHeaderSha256','accepted_budget.h'),
                  ('assemblyPatchSha256','ngspice-47-capacitor-assembly.patch'),
                  ('assemblyHeaderSha256','capacitor_assembly.h')]:
    if provenance[key] != sha(ANALOG/'engine-patches'/name):
        raise ValueError('Build source differs: '+name)
command = [sys.executable, str(ANALOG/'reports/host-represented-time/run.py'), str(a.source),
           '--time-step','represented','--integration-arithmetic','256','--mode','256',
           '--step-divisor',str(a.step_divisor),'--runtime',str(a.runtime),
           '--build-provenance',str(a.build_provenance),'--out',str(a.out)]
env = {k:v for k,v in os.environ.items() if not k.startswith('ROBOTRON_')}
env['ROBOTRON_CAP_ASSEMBLY'] = a.mode
if a.limit is not None:
    env.update(ROBOTRON_ACCEPTED_LIMIT=str(a.limit), ROBOTRON_ACCEPTED_AFTER=repr(a.after))
if not a.review_existing:
    subprocess.run(command, env=env, check=True)
result = json.loads((a.out/'report.json').read_text())
parent = json.loads((a.source/'report.json').read_text())
if (result['sourceReportSha256'] != sha(a.source/'report.json') or
        result['ngspiceRuntime']['executable']['sha256'] != sha(a.runtime) or
        result['artifacts']['build-provenance.json'] != sha(a.build_provenance) or
        result['timestep']['divisor'] != a.step_divisor):
    raise ValueError('Existing producer inputs differ')
for name,digest in result['artifacts'].items():
    if sha(a.out/name) != digest:
        raise ValueError('Changed producer artifact: '+name)
notices = []
assembly = []
with (a.out/'ngspice.log').open() as stream:
    for line in stream:
        if line.startswith('ACCEPTED_BUDGET '): notices.append(line.strip())
        if line.startswith('CAP_ASSEMBLY mode='): assembly.append(line.strip())
if assembly != ['CAP_ASSEMBLY mode='+str(int(a.mode == 'exact'))]:
    raise ValueError('Assembly mode not confirmed')
stops = [line for line in notices if line.startswith('ACCEPTED_BUDGET stopped ')]
if a.limit is None and notices:
    raise ValueError('Unexpected budget enabled')
endpoint = {}
if a.limit is not None:
    endpoint = budget_stop(notices,(a.out/'io.cir').read_text(),a.limit,a.after,result['stopSeconds'])
    for name, waveform in result['waveforms'].items():
        if abs(waveform['lastSampleSeconds']-endpoint['acceptedSeconds']) > 1e-18:
            raise ValueError('Accepted output differs from budget boundary: '+name)
    if result['completed'] or result['solverDiagnostic']:
        raise ValueError('Operational truncation misclassified')
identical = {name:sha(a.out/name)==parent['artifacts'][name] for name in
             ('io.cir','trace.txt','host-trace.txt','driver-trace.txt','boundary-trace.txt')}
control = (a.mode == 'off' and a.limit is None and a.step_divisor == 1)
passed = control and all(identical.values()) and result['solverDiagnostic'] == parent['solverDiagnostic']
receipt = {'qualified':False, 'completed':result['completed'], 'operationallyTruncated':bool(stops),
           'command':command, 'environment':{k:v for k,v in env.items() if k.startswith('ROBOTRON_')},
           'notices':notices,
           'endpoint':endpoint, 'endpointReviewerSha256':sha(ANALOG/'accepted_capture_review.py'),
           'reviewExisting':a.review_existing, 'runnerSha256':sha(__file__), 'reportSha256':sha(a.out/'report.json'),
           'sourceReportSha256':sha(a.source/'report.json'), 'identicalArtifacts':identical,
           'disabledControlPassed':passed, 'waveforms':result['waveforms'],
           'boundary':'Accepted-state output only; not a restart checkpoint, completed refinement or convergence result.'}
(a.out/'capture-control.json').write_text(json.dumps(receipt,indent=2)+'\n')
if control and not passed:
    raise ValueError('Disabled control changed')
print(a.out/'capture-control.json')
