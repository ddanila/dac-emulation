"""Replay every retained sample and independently validate producer completion logs."""
import argparse
import hashlib
import json
import lzma
from pathlib import Path
import re

from filter_truncation_log import diagnostic
from raw_stream_review import compare_streams


def replay(root):
    root=Path(root)
    report=json.loads((root/'transport.json').read_text())
    if report.get('completed') is not True or report.get('qualified') is not False:
        raise ValueError('Invalid transport status')
    if any(len(report[k])!=n for k,n in (('logs',3),('streams',3),('rawArchives',3),('comparisons',2))):
        raise ValueError('Missing stream evidence')
    limits=report['storageLimits']
    if set(limits)!= {'logicalLogBytes','compressedLogBytes','logLineBytes','logicalRawBytes','compressedRawBytes'} or any(type(v) is not int or v<=0 for v in limits.values()):
        raise ValueError('Invalid storage caps')
    usage={k:0 for k in limits if k!='logLineBytes'}
    counts=[]
    for i in range(3):
        path=root/f'{i}.log.xz';digest=hashlib.sha256();size=0;found=[]
        usage['compressedLogBytes']+=path.stat().st_size
        with lzma.open(path,'rb') as stream:
            while True:
                data=stream.readline(limits['logLineBytes']+1)
                if not data:break
                if len(data)>limits['logLineBytes']:raise ValueError('Oversized retained log line')
                size+=len(data);digest.update(data)
                if usage['logicalLogBytes']+size>limits['logicalLogBytes']:raise ValueError('Retained log exceeds cap')
                line=data.decode('utf-8')
                if diagnostic(line) or 'SORRY:' in line:raise ValueError('Retained producer diagnostic')
                found.extend(map(int,re.findall(r'No\. of Data Rows\s*:\s*(\d+)',line)))
                if len(found)>1:raise ValueError('Duplicate completion')
        if len(found)!=1 or report['logs'][i]!={'sha256':digest.hexdigest(),'bytes':size,'samples':found[0]}:
            raise ValueError('Changed completion log')
        counts.append(found[0]);usage['logicalLogBytes']+=size
        usage['compressedRawBytes']+=(root/f'{i}.raw.xz').stat().st_size
    if any(usage[k]>limits[k] for k in usage):
        raise ValueError('Retained storage exceeds cap')
    sizes=[s['bytes'] for s in report['streams']]
    if any(type(size) is not int or size<=0 for size in sizes) or sum(sizes)>limits['logicalRawBytes']:
        raise ValueError('Invalid raw size budget')
    class LimitedReader:
        def __init__(self,stream,limit):self.stream=stream;self.remaining=limit
        def take(self,method,size):
            data=method(min(size,self.remaining+1))
            self.remaining-=len(data)
            if self.remaining<0:raise ValueError('Retained raw exceeds declared size')
            return data
        def read(self,size):return self.take(self.stream.read,size)
        def readline(self,size):return self.take(self.stream.readline,size)
    streams=[];comparisons=[]
    for i in range(2):
        end=report['streams'][i]['endSeconds']
        with lzma.open(root/f'{i}.raw.xz','rb') as left,lzma.open(root/f'{i+1}.raw.xz','rb') as right:
            result=compare_streams(LimitedReader(left,sizes[i]),LimitedReader(right,sizes[i+1]),end,lambda:counts[i:i+2])
        if result['comparison']!=report['comparisons'][i] or result['streams']!=report['streams'][i:i+2]:
            raise ValueError('Changed retained waveform comparison')
        comparisons.append(result['comparison'])
        streams.extend(result['streams'] if i==0 else result['streams'][1:])
    for i,row in enumerate(streams):
        expected={'sha256':row['sha256'],'bytes':row['bytes'], 'compressedBytes':(root/f'{i}.raw.xz').stat().st_size}
        if report['rawArchives'][i]!=expected:raise ValueError('Changed raw archive receipt')
        usage['logicalRawBytes']+=row['bytes']
    if usage!=report['storageUsage'] or any(usage[k]>limits[k] for k in usage):
        raise ValueError('Storage cap/accounting mismatch')
    return {'replayed':True,'streams':streams,'comparisons':comparisons,'storageUsage':usage,'qualified':False}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root',type=Path)
    args=parser.parse_args()
    print(json.dumps(replay(args.root),indent=2))
