#!/usr/bin/env python3
"""Require actual firmware bus activity after the restored memory fault."""
import argparse,json,math
from pathlib import Path
import memory_continue_review as continuation
from memory_continue_review import inventory,preflight
from fast_audit_log import records


def activity(path,fault_seconds,end_seconds=20e-6):
    if not math.isfinite(fault_seconds) or not 0<fault_seconds<end_seconds:raise ValueError('Invalid post-fault activity window')
    previous=-1;later=[];count=0
    for line in records(path,('BUS_EDGE_PS ',)):
        fields=line.split()
        if len(fields)!=2:raise ValueError('Invalid bus activity record')
        tick=int(fields[1]);count+=1
        if tick<=previous or tick<0 or tick>round(end_seconds*1e12):raise ValueError('Invalid bus activity time')
        previous=tick
        if tick>round(fault_seconds*1e12):later.append(tick)
    if not later:raise ValueError('Missing post-fault firmware bus activity')
    return dict(totalBusEdges=count,postFaultBusEdges=len(later),firstPostFaultEdgePS=later[0],lastPostFaultEdgePS=later[-1])


def review(root):
    result=continuation.review(root);found={}
    for mode,state in result['negativeControls'].items():
        target=state['fault']['targetSeconds'];found[mode]=activity(root/mode/'ngspice.log',target)
        if found[mode]!=activity(root/'baseline/ngspice.log',target):raise ValueError('Changed post-fault activity')
    result['postFaultActivity']=found
    result['scope']+=' Nonempty post-fault firmware bus activity is required and matches the original reference.'
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();a.out.write_text(json.dumps(review(a.root),indent=2)+'\n')
