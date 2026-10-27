#!/usr/bin/env python3
"""Compare every retained pre-fault sample with the reviewed full reference prefix."""
import argparse,json,math,struct
from pathlib import Path
import memory_late_review as faults
from memory_late_review import inventory,preflight
from raw_waveform import header
from trace_io import open_binary
from compare_firmware_io import sha as logical_sha


def compare_prefix(candidate,reference,boundary):
    with open_binary(candidate) as a,open_binary(reference) as b:
        names,declared=header(a);other,_=header(b)
        if names!=other or len(names)<2:raise ValueError('Changed prefix observation scope')
        row=struct.Struct('='+'d'*len(names));count=0;last=-math.inf
        while True:
            data=a.read(row.size)
            if not data:break
            if len(data)!=row.size:raise ValueError('Truncated prefix row')
            values=row.unpack(data)
            if not all(map(math.isfinite,values)) or values[0]<=last or (not count and values[0]!=0):raise ValueError('Invalid prefix time or value')
            if data!=b.read(row.size):raise ValueError('Different reference prefix sample: '+str(count))
            last=values[0];count+=1
        if count<2 or declared not in (0,count) or count*2!=boundary['index'] or last>=boundary['targetSeconds']:raise ValueError('Prefix count/time does not match fault hook')
        return dict(allRetainedSampleBytesExactlyEqual=True,samples=count,lastSampleSeconds=last,faultTargetSeconds=boundary['targetSeconds'],nativeHookIndex=boundary['index'],signals=names[1:])


def review(root):
    result=faults.review(root);base=json.loads((root/'baseline/run.json').read_text())
    if logical_sha(root/'baseline/waveform.raw')!=base['storage']['waveform.raw']['sha256']:raise ValueError('Changed reviewed reference waveform')
    result['referencePrefixes']={mode:compare_prefix(root/mode/'waveform.raw',root/'baseline/waveform.raw',state['fault']) for mode,state in result['negativeControls'].items()}
    result['scope']+=' Every retained pre-fault waveform sample is byte-exact against the reviewed normal reference; its sample count matches half the native fault-hook serial. This does not compare post-fault continuation or the complete 20-us trajectory.'
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();a.out.write_text(json.dumps(review(a.root),indent=2)+'\n')
