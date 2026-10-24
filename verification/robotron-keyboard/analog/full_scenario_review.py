#!/usr/bin/env python3
"""Check complete raw capture extent and serial windows; not electrical qualification."""
import argparse
import json
import math
from pathlib import Path
import re
from compare_firmware_io import sha
from filter_truncation_log import diagnostic
from io_scenario import load, observe
from live_raw_review import signal_name
from raw_waveform import header, rows
from scenario_capture import endpoint_ns
from serial_observation import validate_transport
from trace_io import open_binary, open_text


def review(root):
    r=json.loads((root/'run.json').read_text())
    if r.get('error') or r['exitCode']!=0 or r['timedOut'] or r['solverDiagnostic'] or r.get('haltNs') is not None:
        raise ValueError('Incomplete or failed capture')
    if not r.get('rawOutput') or not r.get('fullScenario'):
        raise ValueError('Need an explicit full-scenario raw capture')
    scenario=load(root/'scenario.json')
    if sha(root/'scenario.json')!=r['fullScenario']['sha256']:
        raise ValueError('Changed scenario')
    deck=(root/'io.cir').read_text()
    end_ns=endpoint_ns(deck,scenario,r['stopNs'])
    if end_ns!=r['fullScenario']['endNs'] or sha(root/'io.cir')!=r['deckSha256']:
        raise ValueError('Changed capture endpoint or deck')
    for name,digest in r['inputs'].items():
        if sha(root/name)!=digest:raise ValueError('Changed capture input')
    storage=r['compressedOutput']
    if storage['error'] or storage['format']!='xz' or set(storage['streams'])!={'waveform.raw'}:
        raise ValueError('Incomplete raw storage')
    if sha(root/'waveform.raw')!=storage['streams']['waveform.raw']['sha256']:
        raise ValueError('Changed raw samples')
    counts=[];serial=[]
    with open_text(root/'ngspice.log') as stream:
        for line in stream:
            if diagnostic(line) or 'SORRY:' in line:raise ValueError('Solver/HDL diagnostic')
            counts.extend(re.findall(r'No\. of Data Rows\s*:\s*(\d+)',line))
            if line.startswith('SERIAL_'):serial.append(line.rstrip('\n'))
    if len(counts)!=1:raise ValueError('Missing unique complete sample count')
    count=int(counts[0]);end=end_ns*1e-9
    with open_binary(root/'waveform.raw') as stream:
        names,declared=header(stream)
        names=[signal_name(n) for n in names]
        expected=['time',*[signal_name(n) for n in r['observationSignals']]]
        if len(set(names))!=len(names) or set(names)!=set(expected):
            raise ValueError('Missing or ambiguous saved observations')
        saves=re.findall(r'^\.save (.*)$',deck,re.M)
        if len(saves)!=1 or {signal_name(n) for n in saves[0].split()}!=set(expected[1:]):
            raise ValueError('Saved scope differs from receipt')
        if declared not in (0,count):raise ValueError('Raw header count differs from completion')
        last=None
        for index,sample in enumerate(rows(stream,len(names),count)):
            if index==0 and sample[0]!=0:raise ValueError('Skipped startup')
            last=sample[0]
        if last is None or abs(last-end)>2*math.ulp(end):raise ValueError('Incomplete scenario endpoint')
    transport=validate_transport('\n'.join(serial),require_activity=any(w['minimumBits'] for w in scenario['observations']))
    for events in (transport['transmitted'],transport['received']):
        if any(stamp*1e-12>end for stamp,_ in events):raise ValueError('Serial event outside captured interval')
    coverage={kind:observe(scenario,transport[key],electrical=True)
              for kind,key in (('transmitted','transmitted'),('received','received'))}
    return {'captureComplete':True,'samples':count,'endSeconds':end,'observedSignals':names[1:],
            'serialCoverage':coverage,'serialWindowsPassed':all(v['passed'] for v in coverage.values()),
            'qualified':False,'artifacts':{n:sha(root/n) for n in ('run.json','scenario.json','io.cir','ngspice.log','waveform.raw')},
            'boundary':'Complete saved-sample and serial-window coverage only. Firmware-reference agreement, bus voltage/timing, numerical refinements, coupled rollback and device admission remain separate gates.'}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();a.out.write_text(json.dumps(review(a.run),indent=2)+'\n')
