#!/usr/bin/env python3
"""Extract actual bracketing samples for failed drain-refinement maxima."""
import argparse,json,math
from pathlib import Path
from raw_waveform import header,rows
from trace_io import open_binary
from live_raw_review import signal_name
from ttl7406_probe import sha


def brackets(path,count,targets,end):
    pending=sorted(targets,key=lambda x:x[2]);result={};j=0
    with open_binary(path) as stream:
        names,declared=header(stream);names=[signal_name(n) for n in names]
        if declared not in (0,count):raise ValueError('Wrong raw count')
        previous=None;last=None
        for row in rows(stream,len(names),count):
            if previous is None and row[0]!=0:raise ValueError('Wrong raw start')
            while previous is not None and j<len(pending) and pending[j][2]<=row[0]:
                key,name,t=pending[j];index=names.index(name)
                if not previous[0]<=t<=row[0]:raise ValueError('Target outside bracket')
                fraction=(t-previous[0])/(row[0]-previous[0]);value=previous[index]+fraction*(row[index]-previous[index])
                result[key]=dict(timeSeconds=t,before=[previous[0],previous[index]],after=[row[0],row[index]],fraction=fraction,interpolatedValue=value);j+=1
            previous=row;last=row[0]
        if j!=len(pending) or abs(last-end)>2*math.ulp(end):raise ValueError('Incomplete maximum witness')
    return result


def run(assessment,folders,out):
    r=json.loads(assessment.read_text());targets={n:[] for n in folders};pairs={'coarseFine':('coarse','fine'),'fineFinest':('fine','finest')};identities={}
    for pair,levels in pairs.items():
        for name in r['voltageGate']['failures']:
            t=r['comparisons'][pair]['signals'][name]['timeSeconds'];key=pair+':'+name
            for level in levels:targets[level].append((key,name,t))
    witnesses={}
    for level,folder in folders.items():
        if sha(folder/'run.json')!=r['receipts'][level]:raise ValueError('Changed reviewed receipt')
        p=folder/'waveform.raw.xz';identities[level]=dict(bytes=p.stat().st_size,sha256=sha(p))
        witnesses[level]=brackets(folder/'waveform.raw',r['logs'][level]['count'],targets[level],0.00116)
        if sha(p)!=identities[level]['sha256']:raise ValueError('Changed waveform during witness scan')
    result={}
    for pair,(left,right) in pairs.items():
        for name in r['voltageGate']['failures']:
            key=pair+':'+name;a=witnesses[left][key];b=witnesses[right][key];difference=abs(a['interpolatedValue']-b['interpolatedValue'])
            if difference!=r['comparisons'][pair]['signals'][name]['maximumAbsoluteDifference']:raise ValueError('Brackets do not reproduce maximum')
            result[key]=dict(left=a,right=b,absoluteDifference=difference)
    out.write_text(json.dumps(dict(qualified=False,assessmentSha256=sha(assessment),archives=identities,witnesses=result,scope='Actual neighboring samples exactly reproduce the reported absolute-time maxima. Local witnesses do not independently establish global maxima, numerical convergence or a cause of the discrepancy.'),indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('assessment','coarse','fine','finest','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();run(a.assessment,{n:getattr(a,n) for n in ('coarse','fine','finest')},a.out)
