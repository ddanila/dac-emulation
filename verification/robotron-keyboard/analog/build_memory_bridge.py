#!/usr/bin/env python3
"""Include guarded memory identities and names in complete snapshots and compact logs."""
import argparse,json
from pathlib import Path
import build_parameter_fault_bridge as base
from build_startup_callback_bridge import once
from ttl7406_probe import sha
PREVIOUS_HEADER=base.fault_header
HELPER=r'''
static int robotron_memory_inventory(FILE*out,struct ng_vvp*ctx)
{
    int(*memory)(FILE*)=dlsym(ctx->vvp_handle,"robotron_vvp_memory_metadata_inventory");
    return memory?memory(out):-1;
}
'''


def memory_header(header):
    header='static int robotron_memory_inventory(FILE*,struct ng_vvp*);\n'+PREVIOUS_HEADER(header)+'\n'+HELPER
    header=once(header,'robotron_parameter_inventory(f, ctx) || fprintf(f, "VA_END\\n")','robotron_parameter_inventory(f, ctx) || robotron_memory_inventory(f, ctx) || fprintf(f, "VA_END\\n")')
    header=once(header,'robotron_metadata_previous[5]','robotron_metadata_previous[6]')
    header=once(header,'robotron_metadata_sequence[5]','robotron_metadata_sequence[6]')
    header=once(header,'if(q&&(!start||q<start))start=q;','if(q&&(!start||q<start))start=q;\n        const char*t=strstr(cursor,"VMM_BEGIN ");if(t&&(!start||t<start))start=t;')
    header=once(header,'unsigned index=start==q?4:', 'unsigned index=start==t?5:start==q?4:')
    header=once(header,'const char*tag=index==4?"VPMD":','const char*tag=index==5?"VMMD":index==4?"VPMD":')
    header=once(header,'strstr(start,index==4?"\\nVPM_END ":','strstr(start,index==5?"\\nVMM_END ":index==4?"\\nVPM_END ":')
    header=once(header,'sscanf(start,index==4?"VPM_BEGIN %u %llu":','sscanf(start,index==5?"VMM_BEGIN %u %llu":index==4?"VPM_BEGIN %u %llu":')
    return header


def build(source,vpi,vpi_header,out):
    try:
        base.fault_header=memory_header;base.build(source,vpi,vpi_header,out)
    finally:base.fault_header=PREVIOUS_HEADER
    p=out/'build.json';r=json.loads(p.read_text());r['sources'][str(Path(__file__).resolve())]=sha(Path(__file__))
    r['scope']='Native memory identity/name images participate in complete dense snapshot comparison. Exact body reuse occurs only at serialized log output. Prior parameter/signal/port modes remain. Memory-specific faults and operational integration remain separate.'
    p.write_text(json.dumps(r,indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('source','vpi','vpi-header','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();build(a.source,a.vpi,a.vpi_header,a.out)
