#!/usr/bin/env python3
"""Enforce parameter-log budgets before the unchanged complete board review."""
import argparse,json
from pathlib import Path
from scope_signals_recovery_gate import require
from parameter_operational_review import assess as original_assess


def budgets(root):
    modes=('off','observe','callback-list-user-corrupt','callback-list-object-corrupt','callback-list-function-corrupt','callback-list-link-corrupt')+tuple('parameter-'+n+'-corrupt' for n in ('word','signed','sized','local','file','line','name','width','scope','name-pointer'))
    results={}
    for mode in modes:
        r=json.loads((root/mode/'run.json').read_text());log=r.get('log',{})
        if r.get('startupOnly') is not False or not r.get('completed') or r.get('error') or r.get('captureTimeoutSeconds')!=3300:raise ValueError('Incomplete bounded parameter capture')
        if log.get('logicalLimitBytes')!=76*1024**3 or log.get('compressedLimitBytes')!=256*1024**2:raise ValueError('Changed parameter log limits')
        for key,cap in (('bytes',76*1024**3),('compressedBytes',256*1024**2)):
            if type(log.get(key)) is not int or not 0<log[key]<=cap:raise ValueError('Parameter log exceeds bounded size')
        if (root/mode/'ngspice.log.xz').stat().st_size!=log['compressedBytes']:raise ValueError('Compressed parameter size differs')
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
