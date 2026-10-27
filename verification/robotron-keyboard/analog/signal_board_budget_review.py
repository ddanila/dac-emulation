#!/usr/bin/env python3
"""Enforce signal-log budgets before the unchanged complete board review."""
import argparse,json
from pathlib import Path
from wire_recovery_gate import require
from signal_board_review import assess as original_assess


def budgets(root):
    modes=('off','observe','signal-init-corrupt','signal-value-corrupt','signal-active-corrupt')
    results={}
    for mode in modes:
        r=json.loads((root/mode/'run.json').read_text());log=r.get('log',{})
        if not r.get('completed') or r.get('error') or r.get('captureTimeoutSeconds')!=3060:raise ValueError('Incomplete bounded signal capture')
        if log.get('logicalLimitBytes')!=16*1024**3 or log.get('compressedLimitBytes')!=256*1024**2:raise ValueError('Changed signal log limits')
        for key,cap in (('bytes',16*1024**3),('compressedBytes',256*1024**2)):
            if type(log.get(key)) is not int or not 0<log[key]<=cap:raise ValueError('Wire log exceeds bounded size')
        if (root/mode/'ngspice.log.xz').stat().st_size!=log['compressedBytes']:raise ValueError('Compressed signal size differs')
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
