#!/usr/bin/env python3
"""Include all parameter payloads in dense snapshots and compact log output."""
import argparse,json
from pathlib import Path
import build_scope_signal_fault_bridge as base
from build_startup_callback_bridge import once
from ttl7406_probe import sha
PREVIOUS_HEADER=base.fault_header
HELPER=r'''
static int robotron_parameter_inventory(FILE*out,struct ng_vvp*ctx)
{
    int(*parameters)(FILE*)=dlsym(ctx->vvp_handle,"robotron_vvp_parameter_inventory");
    return parameters?parameters(out):-1;
}
'''


def parameter_header(header):
    header='static int robotron_parameter_inventory(FILE*,struct ng_vvp*);\n'+PREVIOUS_HEADER(header)+'\n'+HELPER
    header=once(header,'robotron_scope_signals_inventory(f, ctx) || fprintf(f, "VA_END\\n")','robotron_scope_signals_inventory(f, ctx) || robotron_parameter_inventory(f, ctx) || fprintf(f, "VA_END\\n")')
    header=once(header,'robotron_metadata_previous[4]','robotron_metadata_previous[5]')
    header=once(header,'robotron_metadata_sequence[4]','robotron_metadata_sequence[5]')
    header=once(header,'if(s&&(!start||s<start))start=s;','if(s&&(!start||s<start))start=s;\n        const char*q=strstr(cursor,"VPM_BEGIN ");if(q&&(!start||q<start))start=q;')
    header=once(header,'unsigned index=start==s?3:start==p?2:start==r?1:0;const char*tag=index==3?"VSAD":index==2?"VPPD":index?"VSMRD":"VSMD";','unsigned index=start==q?4:start==s?3:start==p?2:start==r?1:0;const char*tag=index==4?"VPMD":index==3?"VSAD":index==2?"VPPD":index?"VSMRD":"VSMD";')
    header=once(header,'strstr(start,index==3?"\\nVSA_END ":','strstr(start,index==4?"\\nVPM_END ":index==3?"\\nVSA_END ":')
    header=once(header,'sscanf(start,index==3?"VSA_BEGIN %u %llu":','sscanf(start,index==4?"VPM_BEGIN %u %llu":index==3?"VSA_BEGIN %u %llu":')
    return header


def build(source,vpi,vpi_header,out):
    try:
        base.fault_header=parameter_header;base.build(source,vpi,vpi_header,out)
    finally:base.fault_header=PREVIOUS_HEADER
    p=out/'build.json';r=json.loads(p.read_text());r['sources'][str(Path(__file__).resolve())]=sha(Path(__file__))
    r['scope']='Complete native parameter payloads participate in dense full-state equality; independent exact body reuse occurs only when writing logs. Preserves preceding scope/signal/port fault modes. Transient and parameter-specific integrated fault qualification remain separate.'
    p.write_text(json.dumps(r,indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('source','vpi','vpi-header','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();build(a.source,a.vpi,a.vpi_header,a.out)
