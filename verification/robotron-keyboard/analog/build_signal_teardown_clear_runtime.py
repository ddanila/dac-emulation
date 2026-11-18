#!/usr/bin/env python3
"""Remove non-owning signal registrations at native signal_delete entry."""
import argparse,json
from pathlib import Path
import build_signal_teardown_trace_runtime as previous
from ttl7406_probe import sha

def invalidate(out):
    p=out/'vvp/vpi_signal.cc';s=p.read_text()
    old='void signal_delete(vpiHandle item)\n{'
    new=old+'''
      // Native cleanup owns signal lifetime. Drop non-owning metadata before
      // releasing the node and bit/index cache; never reset lifetime IDs.
      size_t registered_before=robotron_handles().size();
      robotron_handles().erase(static_cast<__vpiSignal*>(item));
      if(getenv("ROBOTRON_TEARDOWN_TRACE")) fprintf(stdout,"TEARDOWN_SIGNAL_FORGET %p %zu %zu\\n",(void*)item,registered_before,robotron_handles().size());'''
    if s.count(old)!=1:raise ValueError('Ambiguous native signal deletion boundary')
    p.write_text(s.replace(old,new))

def build(archive,out,bison,jobs):
    out=out.resolve();module=previous
    while hasattr(module,'previous'):module=module.previous
    base=module.base;original=base.subprocess
    class Commands:
        def __getattr__(self,name):return getattr(original,name)
        def run(self,command,**kwargs):
            if command[:3]==['make','-C','vvp']:invalidate(out)
            return original.run(command,**kwargs)
    try:base.subprocess=Commands();previous.build(archive,out,bison,jobs)
    finally:base.subprocess=original
    r=json.loads((out/'build.json').read_text());r['sources'][Path(__file__).name]=sha(Path(__file__))
    r['outputs']['vvp/vpi_signal.cc']=sha(out/'vvp/vpi_signal.cc')
    r['signalTeardown']='Erase the native signal non-owning observer entry at signal_delete entry, before native graph and bit/index release. IDs remain monotonic and the existing full shutdown guard remains closed. Pool allocator and native release semantics are unchanged.'
    (out/'build.json').write_text(json.dumps(r,indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('archive','out','bison'):p.add_argument('--'+n,type=Path,required=True)
    p.add_argument('--jobs',type=int,default=2);a=p.parse_args();build(a.archive,a.out,a.bison,a.jobs)
