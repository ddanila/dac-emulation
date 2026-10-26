#!/usr/bin/env python3
"""Locate queued event classes relative to the actual first firmware fetch."""
import argparse,collections,json
from pathlib import Path
from audit_log import records
from private_queue_board_review import inventory
from compare_firmware_io import sha as logical_sha
from ttl7406_probe import sha


def profile(run):
    receipt=json.loads((run/'run.json').read_text())
    if not receipt['completed'] or receipt.get('error') or receipt['exitCode']!=0 or receipt['mode']!='observe':
        raise ValueError('Need completed board observer capture')
    if ':vpi_time_precision - 12;' not in (run/'io.vvp').read_text():raise ValueError('Need native picosecond scheduler ticks')
    if sha(run/'io.vvp')!=receipt['inputs']['io.vvp']:raise ValueError('Changed compiled HDL')
    if logical_sha(run/'ngspice.log')!=receipt['log']['sha256']:raise ValueError('Changed observer log')
    coverage=inventory(run/'ngspice.log')
    fetches=list(records(run/'ngspice.log',('FIRST_FETCH ',)))
    if len(fetches)!=1:raise ValueError('Missing unique first fetch')
    first=int(fetches[0].split()[1]);stage=None;phase=None
    counts=collections.defaultdict(collections.Counter);boundaries=collections.Counter()
    for line in records(run/'ngspice.log',('VQ_STAGE ','VQ_BEGIN ','VQ_EVENT ')):
        a=line.split()
        if a[0]=='VQ_STAGE':stage=a[1]
        elif a[0]=='VQ_BEGIN' and stage=='before':
            tick=int(a[2]);phase='timeZero' if tick==0 else 'beforeFirstFetch' if tick<first else 'atOrAfterFirstFetch'
            boundaries[phase]+=1
        elif a[0]=='VQ_EVENT' and stage=='before':counts[phase][tuple(a[4:])]+=1
    if sum(boundaries.values())!=coverage['boundaries'] or sum(sum(c.values()) for c in counts.values())!=coverage['queuedEventObservations']:
        raise ValueError('Profile lost observed queue coverage')
    return {'qualified':False,'firstFetchTicks':first,'tickSeconds':1e-12,'captureReceiptSha256':sha(run/'run.json'),
            'phases':{phase:{'boundaries':boundaries[phase],'events':[{'eventClass':key[0],'nestedClass':key[1],'observations':value} for key,value in sorted(counts[phase].items())]} for phase in boundaries},
            'scope':'Each before/repeat observation pair counted once, using the observed native scheduler time rather than the requested bridge target. Event classes are not serialized payloads; no executing-event or rollback claim.',
            'profilerSha256':sha(Path(__file__))}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();result=profile(a.run)
    with a.out.open('x') as f:json.dump(result,f,indent=2);f.write('\n')
