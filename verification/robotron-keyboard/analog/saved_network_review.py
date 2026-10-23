#!/usr/bin/env python3
"""Compare every saved vector in existing complete live captures, without rerunning physics."""
import argparse
import json
import re
from pathlib import Path
from numerical_voltage_budget import voltage_gate
from complete_network_review import review, artifact
from host_waveform_comparison import rows,compare_samples
from gate_switching_probe import sha
from trace_io import open_text

FILES=('network_witness.txt','bus-trace.txt','wr-trace.txt','witness.txt','driver-trace.txt')

def compare_saved(runs,end_seconds):
    result={'completed':False,'electricallyQualified':False,'requiredEndSeconds':end_seconds,'pairs':[]}
    receipts=[json.loads((p/'run.json').read_text()) for p in runs]
    for first in (0,1):
        pair=review(runs[first:first+2],end_seconds)
        covered=set();evidence={}
        for name in FILES:
            paths=[p/name for p in runs[first:first+2]]
            headers=[]
            for path in paths:
                with open_text(path) as stream:headers.append(stream.readline().split())
            if headers[0]!=headers[1] or headers[0][0]!='time':raise ValueError('Inconsistent trace vectors')
            signals=headers[0][1:];covered.update(signals)
            data=compare_samples(*(rows(path,signals,r['stepNs']) for path,r in zip(paths,receipts[first:first+2])))
            if abs(data['endSeconds']-end_seconds)>1e-15:raise ValueError('Incomplete saved vector interval')
            for signal,item in zip(signals,data['signals']):
                metric={'unit':'V' if signal.startswith('v(') else 'A','maximumAbsoluteDifference':item['maximumDifferenceV'],'timeSeconds':item['timeSeconds']}
                if signal in pair['signals'] and pair['signals'][signal]['maximumAbsoluteDifference']!=metric['maximumAbsoluteDifference']:
                    raise ValueError('Duplicate observations disagree')
                pair['signals'][signal]=metric
            evidence[name]=[sha(artifact(p,name)) for p in runs[first:first+2]]
        for directory in runs[first:first+2]:
            saved=set(' '.join(re.findall(r'^\.save (.*)$',(directory/'io.cir').read_text(),re.M)).split())
            if saved!=covered:raise ValueError('Saved-vector coverage differs: '+str(saved.symmetric_difference(covered)))
        pair['allSavedVectorsCompared']=True;pair['additionalArtifacts']=evidence
        result['pairs'].append(pair)
    result['voltage']=voltage_gate(result['pairs']);result['completed']=True
    result['scope']='Complete declared short interval and every saved vector, including receiver and bus/WR observations. This does not cover repeat/release, disabled controls or independent device admission.'
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('runs',nargs=3,type=Path)
    p.add_argument('--end-seconds',required=True,type=float);p.add_argument('--out',required=True,type=Path);a=p.parse_args()
    a.out.write_text(json.dumps(compare_saved(a.runs,a.end_seconds),indent=2)+'\n')
