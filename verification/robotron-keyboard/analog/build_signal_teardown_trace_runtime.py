#!/usr/bin/env python3
"""Trace native signal, bit-cache and pool release after observation closes."""
import argparse,json
from pathlib import Path
import build_native_observer_shutdown_runtime as previous
from ttl7406_probe import sha

def instrument(out):
    p=out/'vvp/vpi_signal.cc';s=p.read_text();guard='if(getenv("ROBOTRON_TEARDOWN_TRACE")) '
    replacements=[
      ('      assert(obj->node->fil);','      '+guard+'fprintf(stdout,"TEARDOWN_SIGNAL_BEGIN %p %p %p %u %d\\n",(void*)obj,(void*)obj->node,(void*)obj->bits,obj->bits?obj->width():0,robotron_vvp_observation_active());\n      assert(obj->node->fil);'),
      ('      signal_dels += 1;','      '+guard+'fprintf(stdout,"TEARDOWN_SIGNAL_RELEASED %p\\n",(void*)obj);\n      signal_dels += 1;'),
      ('void signal_pool_delete()\n{','void signal_pool_delete()\n{\n      '+guard+'fprintf(stdout,"TEARDOWN_SIGNAL_POOLS %u %lu %lu %zu %d\\n",signal_pool_count,signal_count,signal_dels,robotron_handles().size(),robotron_vvp_observation_active());'),
      ('\t    free(signal_pool[idx]);','            '+guard+'fprintf(stdout,"TEARDOWN_SIGNAL_POOL_FREE %u %p\\n",idx,(void*)signal_pool[idx]);\n\t    free(signal_pool[idx]);'),
      ('      signal_pool_count = 0;','      signal_pool_count = 0;\n      '+guard+'fprintf(stdout,"TEARDOWN_SIGNAL_POOLS_DONE %zu\\n",robotron_handles().size());')]
    for old,new in replacements:
        if s.count(old)!=1:raise ValueError('Ambiguous signal teardown trace site')
        s=s.replace(old,new)
    p.write_text(s)

def build(archive,out,bison,jobs):
    out=out.resolve();module=previous
    while hasattr(module,'previous'):module=module.previous
    base=module.base;original=base.subprocess
    class Commands:
        def __getattr__(self,name):return getattr(original,name)
        def run(self,command,**kwargs):
            if command[:3]==['make','-C','vvp']:instrument(out)
            return original.run(command,**kwargs)
    try:base.subprocess=Commands();previous.build(archive,out,bison,jobs)
    finally:base.subprocess=original
    r=json.loads((out/'build.json').read_text());r['sources'][Path(__file__).name]=sha(Path(__file__))
    r['outputs']['vvp/vpi_signal.cc']=sha(out/'vvp/vpi_signal.cc')
    r['signalTeardownTrace']='Diagnostics at native signal_delete entry and after graph/bit-cache release, followed by pool counts and each native pool free. Records observation guard and remaining signal-handle registrations. No erasure or allocation changes; ASAN custom-pool and leak limitations remain.'
    (out/'build.json').write_text(json.dumps(r,indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('archive','out','bison'):p.add_argument('--'+n,type=Path,required=True)
    p.add_argument('--jobs',type=int,default=2);a=p.parse_args();build(a.archive,a.out,a.bison,a.jobs)
