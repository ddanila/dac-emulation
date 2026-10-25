"""Compare complete raw streams before their final producer counts are available.

The caller must drain producer logs independently, and return successful completion
counts only after both producers exit. No success is published before that check.
This is a transport primitive, not full-scenario qualification or a capture launcher.
"""
import hashlib
import math
import struct
from itertools import zip_longest
from raw_waveform import header
from live_raw_review import signal_name
from host_waveform_comparison import compare_samples


class RawStream:
    def __init__(self, stream, end):
        self.stream=stream;self.digest=hashlib.sha256();self.bytes=0;self.count=0
        self.end=end;self.last=None;self.finished=False
        names,self.declared=header(self)
        self.names=[signal_name(n) for n in names]
        if len(set(self.names))!=len(self.names):raise ValueError('Ambiguous observation scope')
        self.row=struct.Struct('='+len(self.names)*'d')

    def read(self, size):
        data=self.stream.read(size);self.digest.update(data);self.bytes+=len(data);return data

    def readline(self, size):
        data=self.stream.readline(size);self.digest.update(data);self.bytes+=len(data);return data

    def samples(self, order):
        while True:
            data=self.read(self.row.size)
            while data and len(data)<self.row.size:
                more=self.read(self.row.size-len(data))
                if not more:raise ValueError('Truncated raw row')
                data+=more
            if not data:break
            row=self.row.unpack(data)
            if not all(map(math.isfinite,row)):raise ValueError('Nonfinite raw row')
            if self.last is None:
                if row[0]!=0:raise ValueError('Waveform must start at zero')
            elif row[0]<=self.last:raise ValueError('Nonmonotonic raw time')
            self.last=row[0];self.count+=1
            yield tuple(row[i] for i in order)
        if self.count<2 or self.last is None or abs(self.last-self.end)>2*math.ulp(self.end):
            raise ValueError('Incomplete declared observation window')
        self.finished=True

    def receipt(self, count):
        if type(count) is not int or count<2 or not self.finished or count!=self.count or self.declared not in (0,count):
            raise ValueError('Producer completion count disagrees with consumed stream')
        return {'sha256':self.digest.hexdigest(),'bytes':self.bytes,'samples':self.count,'endSeconds':self.last}


def compare_streams(left, right, expected_end, completion_counts, *, exact=False):
    if not math.isfinite(expected_end) or expected_end<=0:raise ValueError('Invalid required endpoint')
    a,b=RawStream(left,expected_end),RawStream(right,expected_end)
    if set(a.names)!=set(b.names):raise ValueError('Different observation scope')
    streams=[a.samples(range(len(a.names))),b.samples([b.names.index(n) for n in a.names])]
    if exact:
        for index,(x,y) in enumerate(zip_longest(*streams)):
            if x!=y:raise ValueError('Different raw sample at row '+str(index))
        result={'allSamplesExactlyEqual':True,'samples':a.count,'endSeconds':expected_end,'signals':a.names[1:]}
    else:
        result=compare_samples(*streams)
        result['signals']={name:{'unit':'A' if name.startswith('i(') or name.endswith('[i]') else 'V',
                                 'maximumAbsoluteDifference':value['maximumDifferenceV'],'timeSeconds':value['timeSeconds']}
                           for name,value in zip(a.names[1:],result['signals'])}
        result['maximumVoltageDifference']=max(v['maximumAbsoluteDifference'] for v in result['signals'].values() if v['unit']=='V')
        result['boundary']='All observed samples, piecewise-linear comparison on both absolute-time grids. No alignment or intersample extrema claim.'
    counts=completion_counts()
    if len(counts)!=2:raise ValueError('Need two independently completed producer counts')
    receipts=[s.receipt(count) for s,count in zip((a,b),counts)]
    return {'comparison':result,'streams':receipts,'completed':True,'qualified':False}
