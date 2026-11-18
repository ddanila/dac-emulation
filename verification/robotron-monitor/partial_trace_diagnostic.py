"""Summarize an unfinished ngspice raw trace for debugging, never acceptance.

The solver may leave a valid prefix with an unfinalized point count when it is
stopped. This reader accepts only complete binary rows and labels the result
partial. Voltage means are integrated over time, since adaptive solver rows
are not uniformly spaced.
"""
import argparse
import hashlib
import json
import math
import re
import struct
from pathlib import Path

PROBES=('time','v(h_sync)','v(eht)','v(xcrt.launch_current_ua)')


def summarize(path, window_s=.001):
    if not math.isfinite(window_s) or window_s<=0:
        raise ValueError('diagnostic window must be positive and finite')
    path=Path(path)
    bins=[];digest=hashlib.sha256();previous=None;rows=0;trailing=0
    with path.open('rb') as stream:
        header=b''
        while not header.endswith(b'Binary:\n'):
            line=stream.readline()
            if not line or len(header)>1_000_000:raise ValueError('missing ngspice raw header')
            digest.update(line);header+=line
        header_text=header.decode()
        if 'Flags: real' not in header_text or 'Variables:\n' not in header_text:
            raise ValueError('only real raw traces with a variable table are supported')
        count_match=re.search(r'No. Variables:\s+(\d+)',header_text)
        points_match=re.search(r'No. Points:\s+(\d+)',header_text)
        if not count_match or not points_match:raise ValueError('missing raw vector or point count')
        count=int(count_match[1]);declared=int(points_match[1])
        if not 2<=count<=4096:raise ValueError('unsupported raw vector count')
        names=re.findall(r'^\s*\d+\s+(\S+)\s+\S+\s*$',
                         header_text.split('Variables:\n')[1].split('Binary:')[0],re.M)
        if len(names)!=count or names[0]!='time' or any(name not in names for name in PROBES):
            raise ValueError('raw trace lacks a required diagnostic probe')
        indices=[names.index(name) for name in PROBES]
        unpack=struct.Struct('='+str(count)+'d')
        while data:=stream.read(unpack.size):
            digest.update(data)
            if len(data)<unpack.size:
                trailing=len(data);break
            values=unpack.unpack(data)
            t,sync,eht,launch=(values[i] for i in indices)
            if not all(map(math.isfinite,values)) or t<0 or (previous and t<=previous[0]):
                raise ValueError('invalid raw diagnostic sample')
            slot=int(t/window_s)
            while len(bins)<=slot:
                bins.append(dict(start_s=len(bins)*window_s,samples=0,
                                 h_sync_min_v=float('inf'),h_sync_max_v=-float('inf'),
                                 h_sync_upcross_100v=0,eht_min_v=float('inf'),
                                 eht_max_v=-float('inf'),launch_peak_ua=0.,
                                 duration_s=0.,eht_volt_seconds=0.))
            bucket=bins[slot];bucket['samples']+=1
            bucket['h_sync_min_v']=min(bucket['h_sync_min_v'],sync)
            bucket['h_sync_max_v']=max(bucket['h_sync_max_v'],sync)
            bucket['eht_min_v']=min(bucket['eht_min_v'],eht)
            bucket['eht_max_v']=max(bucket['eht_max_v'],eht)
            bucket['launch_peak_ua']=max(bucket['launch_peak_ua'],launch)
            if previous:
                t0,s0,e0=previous
                if s0<100<=sync:
                    crossing=t0+(100-s0)*(t-t0)/(sync-s0)
                    bins[int(crossing/window_s)]['h_sync_upcross_100v']+=1
                left=t0
                while left<t:
                    segment_bin=min(int(left/window_s),len(bins)-1)
                    right=min(t,(segment_bin+1)*window_s)
                    if right<=left:right=t
                    va=e0+(eht-e0)*(left-t0)/(t-t0)
                    vb=e0+(eht-e0)*(right-t0)/(t-t0)
                    bins[segment_bin]['eht_volt_seconds']+=(va+vb)*(right-left)/2
                    bins[segment_bin]['duration_s']+=right-left
                    left=right
            previous=(t,sync,eht);rows+=1
    if rows<2:raise ValueError('diagnostic trace has fewer than two complete rows')
    for bucket in bins:
        duration=bucket['duration_s']
        bucket['eht_time_mean_v']=bucket.pop('eht_volt_seconds')/duration if duration else None
        if not bucket['samples']:
            for name in ('h_sync_min_v','h_sync_max_v','eht_min_v','eht_max_v'):
                bucket[name]=None
            bucket['launch_peak_ua']=None
    return dict(format='dac-monitor-partial-raw-diagnostic-v1',qualification='diagnostic-only',
                input_sha256=digest.hexdigest(),declared_points=declared,complete_rows=rows,
                trailing_bytes=trailing,last_time_s=previous[0],window_s=window_s,bins=bins)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('trace',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--window-ms',type=float,default=1.)
    args=parser.parse_args()
    result=summarize(args.trace,args.window_ms/1000)
    args.output.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print(f"{result['complete_rows']} rows through {result['last_time_s']:.6f} s; diagnostic only")


if __name__=='__main__':main()
