#!/usr/bin/env python3
"""Enforce raw-wire-log budgets before the unchanged complete board review."""
import argparse,json
from pathlib import Path
from reduction_recovery_gate import require
from raw_wire_board_review import assess as original_assess


def budgets(root):
    modes=('off','observe','raw-wire-corrupt','raw-wire-delayed-corrupt')
    results={}
    for mode in modes:
        r=json.loads((root/mode/'run.json').read_text());log=r.get('log',{})
        if not r.get('completed') or r.get('error') or r.get('captureTimeoutSeconds')!=3300:raise ValueError('Incomplete bounded raw-wire capture')
        if log.get('logicalLimitBytes')!=36*1024**3 or log.get('compressedLimitBytes')!=256*1024**2:raise ValueError('Changed raw-wire log limits')
        for key,cap in (('bytes',36*1024**3),('compressedBytes',256*1024**2)):
            if type(log.get(key)) is not int or not 0<log[key]<=cap:raise ValueError('Raw-wire log exceeds bounded size')
        if (root/mode/'ngspice.log.xz').stat().st_size!=log['compressedBytes']:raise ValueError('Compressed raw-wire size differs')
        results[mode]={k:log[k] for k in ('bytes','compressedBytes','logicalLimitBytes','compressedLimitBytes')}
    return results


def assess(root,producer):
    require(json.loads((root/'baseline-assessment.json').read_text()))
    limits=budgets(root);result=original_assess(root,producer)
    result['captureLogBudgets']=limits
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('root','producer','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();r=assess(a.root,a.producer)
    with a.out.open('x') as f:json.dump(r,f,indent=2);f.write('\n')
