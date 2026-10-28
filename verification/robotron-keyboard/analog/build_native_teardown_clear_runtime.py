#!/usr/bin/env python3
"""Clear native scope observer registrations at final teardown and preserve refusal."""
import argparse,json
from pathlib import Path
import build_native_teardown_trace_runtime as previous
from ttl7406_probe import sha

def invalidate(out):
    p=out/'vvp/vpi_scope.cc';s=p.read_text()
    replacements=[
      ('static set<vpiHandle> robotron_initialized_scopes;', 'static bool robotron_scopes_terminated=false;\nstatic set<vpiHandle> robotron_initialized_scopes;'),
      ('void root_table_delete(void)\n{','void root_table_delete(void)\n{\n      robotron_scopes_terminated=true;'),
      ('static int robotron_static_scopes(vector<__vpiScope*>& scopes)\n{','static int robotron_static_scopes(vector<__vpiScope*>& scopes)\n{\n    if(robotron_scopes_terminated)return -1;'),
      ('      vpip_root_table.clear();','''      vpip_root_table.clear();
      // The native scope traversal has finished. These non-owning registrations
      // must not retain freed scope, signal, port, or port-bit addresses.
      robotron_initialized_scopes.clear();
      robotron_scope_metadata.clear();
      robotron_attached_objects.clear();
      robotron_object_ids.clear();
      robotron_object_types.clear();
      robotron_ports.clear();
      robotron_port_slots.clear();
      robotron_port_bits.clear();
      // IDs remain monotonic. A terminated runtime cannot be observed or reused.''')]
    for old,new in replacements:
        if s.count(old)!=1:raise ValueError('Ambiguous scope teardown invalidation site')
        s=s.replace(old,new)
    p.write_text(s)

def build(archive,out,bison,jobs):
    out=out.resolve();base=previous.previous.base;original=base.subprocess
    class Commands:
        def __getattr__(self,name):return getattr(original,name)
        def run(self,command,**kwargs):
            if command[:3]==['make','-C','vvp']:invalidate(out)
            return original.run(command,**kwargs)
    try:base.subprocess=Commands();previous.build(archive,out,bison,jobs)
    finally:base.subprocess=original
    r=json.loads((out/'build.json').read_text());r['sources'][Path(__file__).name]=sha(Path(__file__))
    r['scopeTeardown']='Native root teardown first marks observer scope state terminated, then clears eight non-owning registration containers after native traversal finishes. Scope-dependent observation refuses permanently; monotonic object IDs are not reset. Existing selected/continuous runtimes are unchanged.'
    (out/'build.json').write_text(json.dumps(r,indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('archive','out','bison'):p.add_argument('--'+n,type=Path,required=True)
    p.add_argument('--jobs',type=int,default=2);a=p.parse_args();build(a.archive,a.out,a.bison,a.jobs)
