#!/usr/bin/env python3
"""Restore a selected later parameter fault and resume normal board execution."""
import argparse,json
from pathlib import Path
import build_memory_bridge as base
from build_startup_callback_bridge import once
from ttl7406_probe import sha
PREVIOUS=base.memory_header


def continue_header(header):
    header=PREVIOUS(header)
    header=once(header,'    static unsigned long long ordinal;','')
    marker='    struct ng_vvp *ctx = (struct ng_vvp*)info->handle;'
    header=once(header,marker,'''    static unsigned long long ordinal;
    static int parameter_fault_done;
    if(parameter_fault_done)return;
    if(strncmp(mode,"parameter-",10))exit(3);
    if(ordinal && (info->vtime<5e-6 || strcmp(phase,"before-step"))){++ordinal;return;}
'''+marker)
    header=once(header,'if(parameter_field>=0 && robotron_start_phase==1){','if(parameter_field>=0 && info->vtime>=5e-6){')
    return once(header,'exit(direct_ok&&equal&&(parameter_field<7?changed_ok:rejected)?2:3);','''if(!(direct_ok&&equal&&(parameter_field<7?changed_ok:rejected)))exit(3);
        parameter_fault_done=1;return;''')


def build(source,vpi,vpi_header,out):
    try:base.memory_header=continue_header;base.build(source,vpi,vpi_header,out)
    finally:base.memory_header=PREVIOUS
    p=out/'build.json';r=json.loads(p.read_text());r['sources'][str(Path(__file__).resolve())]=sha(Path(__file__))
    r['scope']='Startup and selected 5-us parameter fault snapshots include memory metadata. Exact restoration precedes normal execution with further observations disabled. Full continuation comparison required; no unobserved private lifetime coverage.'
    p.write_text(json.dumps(r,indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('source','vpi','vpi-header','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();build(a.source,a.vpi,a.vpi_header,a.out)
