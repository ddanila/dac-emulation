#!/usr/bin/env python3
"""Avoid ASAN interposition of the fixed system VPI loader table in board controls."""
import argparse,json
from pathlib import Path
import build_native_teardown_clear_runtime as previous
from ttl7406_probe import sha

def build(archive,out,bison,jobs):
    out=out.resolve();base=previous.previous.previous.base;original=base.subprocess;changed=False
    class Commands:
        def __getattr__(self,name):return getattr(original,name)
        def run(self,command,**kwargs):
            nonlocal changed
            if command[:3]==['make','-C','vpi'] and not changed:
                p=out/'vpi/sys_table.c';s=p.read_text();old='void (*vlog_startup_routines[])(void) = {'
                if s.count(old)!=1:raise ValueError('Ambiguous VPI loader table')
                p.write_text(s.replace(old,'__attribute__((no_sanitize("address"))) '+old));changed=True
            return original.run(command,**kwargs)
    try:base.subprocess=Commands();previous.build(archive,out,bison,jobs)
    finally:base.subprocess=original
    if not changed:raise ValueError('No loader-table adjustment')
    r=json.loads((out/'build.json').read_text());r['sources'][Path(__file__).name]=sha(Path(__file__))
    r['outputs']['vpi/sys_table.c']=sha(out/'vpi/sys_table.c')
    r['loaderTableExclusion']='Only system.vpi vlog_startup_routines is excluded from ASAN global instrumentation. VPI modules intentionally export this common table name; dyld interposition otherwise poisons unrelated ivlng.vpi globals. Other code and runtime allocations remain instrumented. This does not qualify accesses to the loader table.'
    (out/'build.json').write_text(json.dumps(r,indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('archive','out','bison'):p.add_argument('--'+n,type=Path,required=True)
    p.add_argument('--jobs',type=int,default=2);a=p.parse_args();build(a.archive,a.out,a.bison,a.jobs)
