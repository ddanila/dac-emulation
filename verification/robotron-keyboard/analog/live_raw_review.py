#!/usr/bin/env python3
"""Compare complete direct raw samples with pinned live in-memory waveforms."""
import argparse
import itertools
import json
import math
from pathlib import Path
import re
from live_raw_output import raw_deck
from network_refinement_review import events
from raw_waveform import header, rows
from trace_io import open_binary, open_text
from compare_firmware_io import sha


def signal_name(name):
    # ngspice fileInit_pass2 wraps special current vectors in i(...), whereas
    # wrdata retains the original @device[i] expression. This is naming only.
    return re.sub(r'^i\((@[^\s()]+\[i\])\)$', r'\1', name.lower())


def compare_trace(raw_path, text_path, count):
    with open_binary(raw_path) as raw, open_text(text_path) as text:
        names, declared = header(raw)
        if declared not in (0,count):
            raise ValueError('Raw header disagrees with completed log count')
        columns = text.readline().split()
        lowered = [signal_name(n) for n in names]
        if len(set(lowered)) != len(lowered):
            raise ValueError('Ambiguous raw observation names')
        if not columns or columns[0] != 'time' or len(set(columns)) != len(columns):
            raise ValueError('Invalid baseline columns')
        try:
            selection = [lowered.index(signal_name(n)) for n in columns]
        except ValueError as exc:
            raise ValueError('Missing raw observation') from exc
        first = last = None
        for index,(sample,line) in enumerate(itertools.zip_longest(rows(raw,len(names),count),text)):
            if sample is None or line is None:
                raise ValueError('Different sample counts')
            expected = tuple(map(float,line.split()))
            actual = tuple(sample[i] for i in selection)
            if actual != expected:
                raise ValueError('Different sample at row '+str(index))
            if first is None:
                first = sample[0]
            last = sample[0]
        return {'samples':count,'firstSeconds':first,'lastSeconds':last,'columns':columns,
                'allSamplesExactlyEqual':True}


def review(root, baseline):
    original = json.loads((baseline/'run.json').read_text())
    if original.get('exitCode') != 0 or original.get('timedOut') or original.get('solverDiagnostic') or original.get('haltNs') is not None:
        raise ValueError('Baseline is not a complete unhalted capture')
    if json.loads((root/'baseline.json').read_text()) != original:
        raise ValueError('Changed baseline receipt')
    captures = [json.loads((root/n/'run.json').read_text()) for n in ('memory','pipe')]
    for label,r in zip(('memory','pipe'),captures):
        if r.get('error') or r['exitCode'] != 0 or r['timedOut'] or r['solverDiagnostic']:
            raise ValueError('Incomplete live control')
        if r['mode'] != label or r['baselineRunSha256'] != sha(baseline/'run.json'):
            raise ValueError('Wrong baseline or mode')
        if r['deckSha256'] != sha(root/label/'io.cir'):
            raise ValueError('Changed capture deck')
        for name,digest in r['inputs'].items():
            if sha(root/label/name) != digest:
                raise ValueError('Changed firmware input')
    for key in ('runtime','externalDependencies','inputs','environment'):
        if captures[0][key] != captures[1][key]:
            raise ValueError('Changed paired '+key)
    original_deck=(baseline/'io.cir').read_text()
    if sha(baseline/'io.cir') != original['deckSha256']:
        raise ValueError('Changed baseline deck')
    transformed,writers=raw_deck(original_deck)
    if (root/'memory/io.cir').read_text()!=original_deck or (root/'pipe/io.cir').read_text()!=transformed:
        raise ValueError('Circuit changed beyond output commands')
    completion=json.loads((baseline/'completion-check.json').read_text())
    if completion.get('completed') is not True:
        raise ValueError('Baseline completion is unproven')
    extents=completion['traces']
    for name,_ in writers:
        for label in ('memory',):
            if sha(root/label/name)!=extents[name]['sha256'] or captures[0]['storage'][name]['sha256']!=extents[name]['sha256']:
                raise ValueError('Changed in-memory waveform: '+name)
    if sha(root/'pipe/waveform.raw')!=captures[1]['storage']['waveform.raw']['sha256']:
        raise ValueError('Changed raw waveform')
    logs=[]
    for label in ('memory','pipe'):
        with open_text(root/label/'ngspice.log') as stream:log=stream.read()
        for required in ('DAC_ANCHORED enabled single-bit','MPFR_DIAGNOSTIC bits=256','CAP_ASSEMBLY mode=1','POSTCAP_ASSEMBLY mode=1'):
            if required not in log:
                raise ValueError('Missing runtime acknowledgment')
        logs.append(log)
    counts=[re.findall(r'No\. of Data Rows\s*:\s*(\d+)',log) for log in logs]
    if counts[0]!=counts[1] or len(counts[0])!=1:
        raise ValueError('Missing or different complete row counts')
    count=int(counts[0][0])
    comparisons={name:compare_trace(root/'pipe/waveform.raw',root/'memory'/name,count) for name,_ in writers}
    for name,result in comparisons.items():
        expected=extents[name]
        if result['samples']!=expected['samples'] or result['firstSeconds']!=0 or abs(result['lastSeconds']-original['stopNs']*1e-9)>2*math.ulp(original['stopNs']*1e-9):
            raise ValueError('Incomplete observation interval')
    with open_text(baseline/'ngspice.log') as stream:
        event_sets=[events(stream.read()),*(events(log) for log in logs)]
    if not all(e==event_sets[0] for e in event_sets) or not event_sets[0]['latchesMatch']:
        raise ValueError('Firmware events changed')
    return {'allSamplesExactlyEqual':True,'events':event_sets[0], 'traces':comparisons,
            'qualified':False,'boundary':'Complete bounded reset-release output equivalence; no full-repeat, rollback or physical model qualification.'}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('root','baseline','out'):
        p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args()
    a.out.write_text(json.dumps(review(a.root,a.baseline),indent=2)+'\n')
