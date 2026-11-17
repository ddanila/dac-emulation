#!/usr/bin/env python3
"""Export a numerically accepted signal recording without changing its samples."""
import argparse,json,struct
from pathlib import Path
import lab


def export(verification,case,output):
    verification=Path(verification);output=Path(output)
    raw=verification.read_bytes();result=json.loads(raw)
    accepted=result.get('cases',{}).get(case,{})
    if (result.get('format')!='dac-monitor-signal-verification-v1' or
        result.get('status')!='complete' or not result.get('nominal_accepted') or
        result.get('cases',{}).get('nominal',{}).get('status')!='accepted-characterization' or
        case not in result.get('publishable_cases',[]) or
        accepted.get('status')!='accepted-characterization' or
        not all(accepted.get(check,{}).get('passed') is True for check in ('timestep','cable'))):
        raise ValueError('nominal and selected case must pass numerical verification')
    if case not in __import__('signal_path').CASES:raise ValueError('unsupported case')
    data=(verification.parent/case/'base/replay.mcrt').read_bytes()
    if len(data)>64*1024*1024 or data[:8]!=b'DACCRT2\n':raise ValueError('invalid replay')
    size=struct.unpack_from('<I',data,8)[0]
    if size>1024*1024 or size+12>len(data):raise ValueError('invalid header')
    metadata=json.loads(data[12:12+size]);payload=data[12+size:]
    if metadata.get('hashes')!=accepted['hashes'] or metadata.get('signal_case')!=case:
        raise ValueError('verification/replay provenance mismatch')
    chunks=metadata.get('chunks',[])
    if len(chunks)!=1 or chunks[0].get('kind')!='trace' or chunks[0].get('offset')!=0 or chunks[0].get('bytes')!=len(payload) or chunks[0].get('sha256')!=lab.digest(payload):
        raise ValueError('invalid trace payload')
    metadata['numerical_validation']=dict(status='accepted-characterization',
        scope=result['scope'],verification_sha256=lab.digest(raw),
        full_monitor_qualified=False,timestep=accepted['timestep'],cable=accepted['cable'])
    header=json.dumps(metadata,separators=(',',':'),allow_nan=False).encode()
    if len(header)>1024*1024 or len(header)+12+len(payload)>64*1024*1024:raise ValueError('export budget exceeded')
    with output.open('xb') as stream:stream.write(b'DACCRT2\n'+struct.pack('<I',len(header))+header+payload)
    return metadata


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--verification',type=Path,required=True);p.add_argument('--case',default='nominal')
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    export(a.verification,a.case,a.output)
