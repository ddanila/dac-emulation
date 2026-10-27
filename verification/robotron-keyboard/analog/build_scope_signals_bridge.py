#!/usr/bin/env python3
"""Add full registered vector signal snapshots with compact log-only reuse."""
import argparse,json
from pathlib import Path
import build_port_payload_fault_bridge as base
from build_startup_callback_bridge import once
from ttl7406_probe import sha
PREVIOUS_HEADER=base.fault_header
HELPER=r'''
static int robotron_scope_signals_inventory(FILE*out,struct ng_vvp*ctx)
{
    int(*signals)(FILE*)=dlsym(ctx->vvp_handle,"robotron_vvp_scope_signal_inventory");
    return signals?signals(out):-1;
}
'''


def signal_header(header):
    header='static int robotron_scope_signals_inventory(FILE*,struct ng_vvp*);\n'+PREVIOUS_HEADER(header)+'\n'+HELPER
    header=once(header,'robotron_port_payload_inventory(f, ctx) || fprintf(f, "VA_END\\n")','robotron_port_payload_inventory(f, ctx) || robotron_scope_signals_inventory(f, ctx) || fprintf(f, "VA_END\\n")')
    header=once(header,'robotron_metadata_previous[3]','robotron_metadata_previous[4]')
    header=once(header,'robotron_metadata_sequence[3]','robotron_metadata_sequence[4]')
    header=once(header,'if(p&&(!start||p<start))start=p;','if(p&&(!start||p<start))start=p;\n        const char*s=strstr(cursor,"VSA_BEGIN ");if(s&&(!start||s<start))start=s;')
    header=once(header,'unsigned index=start==p?2:start==r?1:0;const char*tag=index==2?"VPPD":index?"VSMRD":"VSMD";','unsigned index=start==s?3:start==p?2:start==r?1:0;const char*tag=index==3?"VSAD":index==2?"VPPD":index?"VSMRD":"VSMD";')
    header=once(header,'strstr(start,index==2?"\\nVPP_END ":index?"\\nVSMR_END ":"\\nVSM_END ")','strstr(start,index==3?"\\nVSA_END ":index==2?"\\nVPP_END ":index?"\\nVSMR_END ":"\\nVSM_END ")')
    header=once(header,'sscanf(start,index==2?"VPP_BEGIN %u %llu":index?"VSMR_BEGIN %u %llu":"VSM_BEGIN %u %llu"','sscanf(start,index==3?"VSA_BEGIN %u %llu":index==2?"VPP_BEGIN %u %llu":index?"VSMR_BEGIN %u %llu":"VSM_BEGIN %u %llu"')
    return header


def build(source,vpi,vpi_header,out):
    try:
        base.fault_header=signal_header;base.build(source,vpi,vpi_header,out)
    finally:base.fault_header=PREVIOUS_HEADER
    p=out/'build.json';r=json.loads(p.read_text());r['sources'][str(Path(__file__).resolve())]=sha(Path(__file__))
    r['scope']='Dense full registered vector signal payloads added to complete native snapshots. Exact body reuse only at log output, with independent sequence. Existing port and scope/callback fault controls remain; full signal fault and transient qualification separate.'
    p.write_text(json.dumps(r,indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('source','vpi','vpi-header','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();build(a.source,a.vpi,a.vpi_header,a.out)
