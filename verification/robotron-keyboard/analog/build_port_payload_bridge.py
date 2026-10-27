#!/usr/bin/env python3
"""Add dense port payload checks and compact port log records to combined state."""
import argparse,json
from pathlib import Path
import build_scope_metadata_fault_bridge as base
from build_startup_callback_bridge import once
from ttl7406_probe import sha
PREVIOUS_HEADER=base.fault_header
HELPER=r'''
static int robotron_port_payload_inventory(FILE*out,struct ng_vvp*ctx)
{
    int(*ports)(FILE*)=dlsym(ctx->vvp_handle,"robotron_vvp_port_payload_inventory");
    return ports?ports(out):-1;
}
'''


def port_header(header):
    header='static int robotron_port_payload_inventory(FILE*,struct ng_vvp*);\n'+PREVIOUS_HEADER(header)+'\n'+HELPER
    header=once(header,'robotron_scope_metadata_inventory(f, ctx) || fprintf(f, "VA_END\\n")','robotron_scope_metadata_inventory(f, ctx) || robotron_port_payload_inventory(f, ctx) || fprintf(f, "VA_END\\n")')
    header=once(header,'robotron_metadata_previous[2]','robotron_metadata_previous[3]')
    header=once(header,'robotron_metadata_sequence[2]','robotron_metadata_sequence[3]')
    header=once(header,'const char*start=!m?r:!r?m:m<r?m:r;','const char*p=strstr(cursor,"VPP_BEGIN ");\n        const char*start=!m?r:!r?m:m<r?m:r;\n        if(p&&(!start||p<start))start=p;')
    header=once(header,'unsigned index=start==r;const char*tag=index?"VSMRD":"VSMD";','unsigned index=start==p?2:start==r?1:0;const char*tag=index==2?"VPPD":index?"VSMRD":"VSMD";')
    header=once(header,'strstr(start,index?"\\nVSMR_END ":"\\nVSM_END ")','strstr(start,index==2?"\\nVPP_END ":index?"\\nVSMR_END ":"\\nVSM_END ")')
    header=once(header,'sscanf(start,index?"VSMR_BEGIN %u %llu":"VSM_BEGIN %u %llu"','sscanf(start,index==2?"VPP_BEGIN %u %llu":index?"VSMR_BEGIN %u %llu":"VSM_BEGIN %u %llu"')
    return header


def build(source,vpi,vpi_header,out):
    try:
        base.fault_header=port_header;base.build(source,vpi,vpi_header,out)
    finally:base.fault_header=PREVIOUS_HEADER
    p=out/'build.json';r=json.loads(p.read_text());r['sources'][str(Path(__file__).resolve())]=sha(Path(__file__))
    r['scope']='All preceding combined scope metadata layers plus complete dense native port payloads. Native comparisons stay dense; port log bodies use exact reuse with independent sequence. No port-specific fault or normal transient qualification.'
    p.write_text(json.dumps(r,indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('source','vpi','vpi-header','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();build(a.source,a.vpi,a.vpi_header,a.out)
