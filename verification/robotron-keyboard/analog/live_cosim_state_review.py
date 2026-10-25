#!/usr/bin/env python3
"""Review bounded live state-observer controls without loading complete logs."""
import argparse
import itertools
import json
import re
from audit_log import scan, equal
from filter_truncation_log import diagnostic
from compare_firmware_io import sha as logical_sha
from ttl7406_probe import sha
from pathlib import Path
from trace_io import open_text
from raw_pair_review import compare_raw


def records(path, summary):
    active=False;objects=set();entries=0;rejections=0;fetch=False;counts=[];prefixes=[];position=0;declared=None
    with open_text(path) as stream:
        for line in stream:
            if line.startswith('state '):
                if not active or position>=len(prefixes) or not line.startswith(prefixes[position]):
                    raise ValueError('Malformed snapshot inventory')
                position+=1;yield line;continue
            if diagnostic(line) or 'SORRY:' in line:raise ValueError('Solver/HDL diagnostic')
            counts.extend(map(int,re.findall(r'No\. of Data Rows\s*:\s*(\d+)',line)))
            if line.startswith('STATE_INVENTORY '):
                if declared is not None:raise ValueError('Multiple inventories')
                declared=int(line.split('items=')[1])
            if line.startswith('STATE_REJECT '):
                if not line.rstrip().endswith(' equal=1'):raise ValueError('Rejected trial changed state')
                rejections+=1;continue
            if line.startswith('STATE_OBJECT '):
                name=line.split()[1]
                if name in objects:raise ValueError('Duplicate inventory')
                objects.add(name)
                prefixes.append("state "+" ".join(line.split()[1:])+" ")
            if line.startswith('STATE_ENTRY '):
                if active:raise ValueError('Nested snapshot')
                active=True;entries+=1;position=0
            elif line=='STATE_END\n':
                if not active:raise ValueError('Orphan snapshot end')
                if position!=len(objects):raise ValueError('Incomplete snapshot inventory')
                active=False
            elif line.startswith('FIRST_FETCH '):fetch=True
            # Simulator banners and timing vary. Compare state and firmware,
            # not profiling text or the intentionally extra rejection records.
            if active or line=='STATE_END\n' or line.startswith(('STATE_OBJECT ','STATE_INVENTORY ')):
                yield line
    if active or not entries or not objects or declared!=len(objects) or len(counts)!=1:raise ValueError('Incomplete live state capture')
    if not any('.cpu.' in n for n in objects) or sum('.rom[' in n for n in objects)!=2048:
        raise ValueError('Missing CPU or ROM state')
    summary.update(entries=entries,objects=len(objects),rejections=rejections,firmwareFetched=fetch,samples=counts[0])


def assess(root):
    runs={mode:json.loads((root/mode/'run.json').read_text()) for mode in ('off','observe','check','corrupt')}
    if any(runs[m]['exitCode']!=0 for m in ('off','observe','check')) or runs['corrupt']['exitCode']!=2:
        raise ValueError('Unexpected producer completion')
    if any(runs[m]['inputs']!=runs['off']['inputs'] for m in runs):raise ValueError('Different stimuli')
    for mode,run in runs.items():
        for name,digest in run['inputs'].items():
            if sha(root/mode/name)!=digest:raise ValueError('Changed run input')
        for name,item in run['storage'].items():
            if logical_sha(root/mode/name)!=item['sha256']:raise ValueError('Changed captured output')
        expected=dict(runs['off']['environment']);expected['ROBOTRON_LIVE_STATE']=mode
        if run['environment']!=expected or run['runtime']!=runs['off']['runtime']:raise ValueError('Different runtime conditions')
    a={};b={}
    sentinel=object()
    for left,right in itertools.zip_longest(records(root/'observe/ngspice.log',a),records(root/'check/ngspice.log',b),fillvalue=sentinel):
        if left!=right:raise ValueError('Live state or firmware continuation differs')
    if a['rejections'] or not b['rejections'] or not a['firmwareFetched']:raise ValueError('Missing rejection or firmware coverage')
    with open_text(root/'corrupt/ngspice.log') as stream:
        if not any('Live rejected trial changed internal state' in line for line in stream):raise ValueError('No corruption detection')
    off=scan(root/'off/ngspice.log')
    if off['diagnostic'] or off['sorry'] or off['count'] is None:raise ValueError('Incomplete disabled control')
    prefix=('FIRST_FETCH ','BUS_','SERIAL_')
    if not all(equal(root/'off/ngspice.log',root/m/'ngspice.log',prefix) for m in ('observe','check')):
        raise ValueError('Observer changed firmware')
    comparisons=[compare_raw(root/'off/waveform.raw',root/m/'waveform.raw',
                            [off['count'],summary['samples']],20e-6,exact=True)
                 for m,summary in [('observe',a),('check',b)]]
    return {'stateAndContinuationPassed':True,'recordOrdering':'Compare state snapshots and timestamped firmware streams independently: merged stdout/stderr buffering changes their interleaving, not event timestamps.','immediateCorruptionDetected':True,'observe':a,'check':b,
            'waveformComparisons':comparisons,'qualified':False,
            'unobservedState':['Complete HDL pending-event queue','XSPICE rotating output history and d_cosim out_vals buffer'],
            'scope':'Bounded coupled observer control with an explicitly shortened reset/traffic stimulus. Exact exposed-state and bridge/input-queue equality around input-barrier rejections and subsequent scheduler entries. No full-repeat, complete pending-event-queue, general rollback or physical-model qualification.'}

def check_manifest(root):
    manifest=json.loads((root/'manifest.json').read_text())
    files={str(p.relative_to(root)):sha(p) for p in root.rglob('*') if p.is_file() and p.name!='manifest.json'}
    if files!=manifest['files'] or sha(Path(__file__))!=manifest['reviewerSha256']:
        raise ValueError('Changed live state evidence or reviewer; replay required')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True)
    p.add_argument('--check-manifest',action='store_true');a=p.parse_args()
    if a.check_manifest:check_manifest(a.root)
    else:
        result=assess(a.root);(a.root/'assessment.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
