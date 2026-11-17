#!/usr/bin/env python3
"""Bounded-memory profiling of native ngspice binary accepted-step output.

Incomplete raw files are useful diagnostics, never accepted simulations. This
reader does not invent rejected-step counts from an accepted-step waveform.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import struct


def profile(raw_path, *, expected_end_s, log_path=None):
    if not math.isfinite(expected_end_s) or expected_end_s<=0:raise ValueError('invalid endpoint')
    digest=hashlib.sha256();header=bytearray()
    with Path(raw_path).open('rb') as stream:
        while not header.endswith(b'Binary:\n'):
            line=stream.readline(65537);header.extend(line)
            if not line or len(header)>65536:raise ValueError('missing or oversized binary raw header')
        digest.update(header);text=header.decode('utf-8')
        if re.search(r'^Flags: real\s*$',text,re.M) is None:raise ValueError('expected real binary vectors')
        n=int(re.search(r'^No. Variables:\s*(\d+)',text,re.M)[1])
        declared=int(re.search(r'^No. Points:\s*(\d+)',text,re.M)[1])
        if not 2<=n<=1024:raise ValueError('invalid vector count')
        names=[m[1] for m in re.finditer(r'^\s*\d+\s+(\S+)\s+\S+\s*$',text,re.M)]
        if len(names)!=n or names[0]!='time':raise ValueError('invalid raw vector table')
        row_format=struct.Struct('='+str(n)+'d')
        previous=None;count=0;bins={};buffer=b'';smallest=None
        while True:
            chunk=stream.read(65536)
            if not chunk:break
            digest.update(chunk);buffer+=chunk
            limit=len(buffer)//row_format.size*row_format.size
            for row in struct.iter_unpack(row_format.format,buffer[:limit]):
                if not all(math.isfinite(v) for v in row) or row[0]<0:
                    raise ValueError('nonfinite or negative-time accepted sample')
                if previous is not None:
                    dt=row[0]-previous[0]
                    if dt<=0:raise ValueError('nonmonotonic accepted samples')
                    bucket=int(row[0]*1000)
                    stat=bins.setdefault(bucket,dict(steps=0,min_dt_s=dt,max_dt_s=dt,subnanosecond_steps=0))
                    stat['steps']+=1;stat['min_dt_s']=min(stat['min_dt_s'],dt)
                    stat['max_dt_s']=max(stat['max_dt_s'],dt)
                    stat['subnanosecond_steps']+=int(dt<1e-9)
                    if smallest is None or dt<smallest['dt_s']:
                        smallest=dict(dt_s=dt,before=dict(zip(names,previous)),after=dict(zip(names,row)))
                previous=row;count+=1
            buffer=buffer[limit:]
    completed=(not buffer and declared==count and count>1 and
               abs(previous[0]-expected_end_s)<=max(1e-15,expected_end_s*1e-10))
    report=dict(format='dac-monitor-solver-profile-v1',completed_endpoint=completed,
                full_monitor_qualified=False,accepted_rows=count,declared_rows=declared,
                expected_end_s=expected_end_s,last_sample=None if previous is None else dict(zip(names,previous)),
                trailing_bytes=len(buffer),raw_sha256=digest.hexdigest(),smallest_step=smallest,
                millisecond_bins=bins,rejected_steps=None,
                rejected_steps_note='Requires instrumented solver counters; not inferable from accepted raw samples.')
    if log_path is not None:
        log=Path(log_path).read_bytes();report['log_sha256']=hashlib.sha256(log).hexdigest()
        text=log.decode(errors='replace')
        for key,pattern in (('peak_rss_kib',r'Maximum resident set size \(kbytes\):\s*([0-9.]+)'),
                            ('user_cpu_s',r'User time \(seconds\):\s*([0-9.]+)'),
                            ('system_cpu_s',r'System time \(seconds\):\s*([0-9.]+)')):
            match=re.search(pattern,text)
            if match:report[key]=float(match[1])
        failed=bool(re.search(r'timestep too small|simulation.*aborted|fatal error|Exit status: [1-9]',text,re.I))
        if failed:report['completed_endpoint']=False
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--raw',type=Path,required=True);p.add_argument('--log',type=Path)
    p.add_argument('--end',type=float,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();result=profile(a.raw,expected_end_s=a.end,log_path=a.log)
    with a.output.open('x') as stream:json.dump(result,stream,indent=2,allow_nan=False);stream.write('\n')
    print(json.dumps({k:result[k] for k in ('completed_endpoint','accepted_rows','last_sample')}))
