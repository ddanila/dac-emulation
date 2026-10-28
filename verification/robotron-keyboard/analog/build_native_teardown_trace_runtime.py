#!/usr/bin/env python3
"""Build isolated ASAN teardown diagnostics without changing registry lifecycle."""
import argparse,json
from pathlib import Path
import build_native_teardown_runtime as previous
from ttl7406_probe import sha

def instrument(out):
    def replace(name,old,new):
        p=out/name;s=p.read_text()
        if s.count(old)!=1:raise ValueError('Ambiguous teardown trace site: '+name)
        p.write_text(s.replace(old,new))
    guard='if(getenv("ROBOTRON_TEARDOWN_TRACE")) '
    replace('vvp/lib_main.cc','static void final_cleanup()\n{','static void final_cleanup()\n{\n      '+guard+'fprintf(stdout,"TEARDOWN_BEGIN\\n");')
    replace('vvp/lib_main.cc','      load_module_delete();','      '+guard+'fprintf(stdout,"TEARDOWN_UNLOAD\\n");\n      load_module_delete();')
    for family in ('Binary','Real','String'):
        old='__vpi'+family+'Param::~__vpi'+family+'Param()\n{'
        replace('vvp/vpi_const.cc',old,old+'\n      '+guard+'fprintf(stdout,"TEARDOWN_PARAMETER '+family+' %p\\n",(void*)this);')
    replace('vvp/vpi_const.cc','    robotron_parameters().erase(p);','    robotron_parameters().erase(p);\n    '+guard+'fprintf(stdout,"TEARDOWN_PARAMETER_REMAIN %zu\\n",robotron_parameters().size());')
    replace('vvp/array.cc','    robotron_memories.erase(static_cast<vpiHandle>(this));','    robotron_memories.erase(static_cast<vpiHandle>(this));\n    '+guard+'fprintf(stdout,"TEARDOWN_MEMORY %p %zu\\n",(void*)this,robotron_memories.size());')
    row='fprintf(stdout,"TEARDOWN_REGISTRIES %s %zu %zu %zu %zu %zu %zu %zu %zu %zu\\n",PHASE,vpip_root_table.size(),robotron_initialized_scopes.size(),robotron_scope_metadata.size(),robotron_attached_objects.size(),robotron_object_ids.size(),robotron_object_types.size(),robotron_ports.size(),robotron_port_slots.size(),robotron_port_bits.size());'
    replace('vvp/vpi_scope.cc','void root_table_delete(void)\n{','void root_table_delete(void)\n{\n      '+guard+row.replace('PHASE','"before"'))
    replace('vvp/vpi_scope.cc','      vpip_root_table.clear();','      vpip_root_table.clear();\n      '+guard+row.replace('PHASE','"after"'))

def build(archive,out,bison,jobs):
    out=out.resolve();original=previous.base.subprocess
    class Commands:
        def __getattr__(self,name):return getattr(original,name)
        def run(self,command,**kwargs):
            if command[:3]==['make','-C','vvp']:instrument(out)
            return original.run(command,**kwargs)
    try:previous.base.subprocess=Commands();previous.build(archive,out,bison,jobs)
    finally:previous.base.subprocess=original
    r=json.loads((out/'build.json').read_text());r['sources'][Path(__file__).name]=sha(Path(__file__))
    r['outputs'].update({n:sha(out/n) for n in ('vvp/lib_main.cc','vvp/vpi_scope.cc','vvp/vpi_const.cc','vvp/array.cc')})
    r['teardownTrace']='Environment-gated diagnostics only: native parameter/memory destruction, root cleanup registry sizes, and VPI unload ordering. No registry erasure or observer semantics changed.'
    (out/'build.json').write_text(json.dumps(r,indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('archive','out','bison'):p.add_argument('--'+n,type=Path,required=True)
    p.add_argument('--jobs',type=int,default=2);a=p.parse_args();build(a.archive,a.out,a.bison,a.jobs)
