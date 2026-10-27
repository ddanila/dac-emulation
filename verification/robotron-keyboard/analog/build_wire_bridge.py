#!/usr/bin/env python3
"""Add lossless full-scan wire payloads to every preceding board layer."""
import argparse,json
from pathlib import Path
import build_net_bridge as base
from build_startup_callback_bridge import once
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent
NET_HEADER=base.net_header
HELPER=r'''
static int robotron_wire_inventory(FILE *f,struct ng_vvp *ctx)
{
    int (*inventory)(FILE*)=dlsym(ctx->vvp_handle,"robotron_vvp_wire_delta_inventory");
    return inventory ? inventory(f) : -1;
}
static int robotron_wire_fault(struct ng_vvp *ctx,int kind,int field)
{
    int (*toggle)(int,int)=dlsym(ctx->vvp_handle,"robotron_vvp_wire_toggle");
    return toggle ? toggle(kind,field) : -1;
}
static void robotron_wire_reference(struct ng_vvp *ctx)
{
    static struct ng_vvp *owner;
    if(owner && owner!=ctx)exit(3);
    if(owner)return;
    int (*reference)(FILE*)=dlsym(ctx->vvp_handle,"robotron_vvp_wire_reference");
    if(!reference || reference(stderr))exit(2);
    owner=ctx;
}
'''
FAULT=r'''
    int wire_kind=strstr(mode,"wire4-")==mode?4:strstr(mode,"wire8-")==mode?8:0;
    int wire_field=strstr(mode,"-init-corrupt")?0:strstr(mode,"-driven-corrupt")?1:strstr(mode,"-propagate-corrupt")?4:-1;
    if(wire_kind && wire_field>=0 && (wire_field==0 ? robotron_start_phase==1 : info->vtime>=5e-6)) {
        if(robotron_wire_fault(ctx,wire_kind,wire_field)!=1)exit(2);
        char *changed=display_snapshot(ctx,api);
        if(robotron_wire_fault(ctx,wire_kind,wire_field)!=1)exit(3);
        char *restored=display_snapshot(ctx,api);
        int detected=changed && strcmp(before,changed)!=0;
        int equal=restored && !strcmp(before,restored);
        if(changed)fprintf(stderr,"VB_STAGE changed\n%s",changed);
        if(restored)fprintf(stderr,"VB_STAGE restored\n%s",restored);
        fprintf(stderr,"VB_WIRE_FAULT kind=%d field=%d changed=%d restored=%d\n",wire_kind,wire_field,detected,equal);
        free(before);free(changed);free(restored);
        exit(detected && equal?2:3);
    }
'''


def wire_header(header):
    header=HELPER+'\n'+NET_HEADER(header)
    header=once(header,'robotron_net_inventory(f, ctx) || fprintf(f, "VA_END\\n")',
                'robotron_net_inventory(f, ctx) || robotron_wire_inventory(f, ctx) || fprintf(f, "VA_END\\n")')
    modes=''.join(' && strcmp(mode,"wire'+str(kind)+'-'+name+'-corrupt")' for kind in (4,8) for name in ('init','driven','propagate'))
    header=once(header,'&& strcmp(mode,"net-foreign-corrupt"))','&& strcmp(mode,"net-foreign-corrupt")'+modes+')')
    header=once(header,'    robotron_net_reference(ctx);','    robotron_net_reference(ctx);\n    robotron_wire_reference(ctx);')
    return once(header,'    int net_field=',FAULT+'\n    int net_field=')


def build(source,vpi,vpi_header,out):
    try:
        base.net_header=wire_header
        base.build(source,vpi,vpi_header,out)
    finally:base.net_header=NET_HEADER
    path=out/'build.json';r=json.loads(path.read_text());r['sources'][str(Path(__file__).resolve())]=sha(Path(__file__))
    r['scope']='All preceding board layers plus lossless full-scan wire payloads. Vec4/vec8 initialization, driven-value and propagation faults restore before execution. Callback-list contents and other functor payloads remain separate.'
    path.write_text(json.dumps(r,indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('source','vpi','vpi-header','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();build(a.source,a.vpi,a.vpi_header,a.out)
