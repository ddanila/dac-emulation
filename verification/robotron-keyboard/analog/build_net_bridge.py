#!/usr/bin/env python3
"""Add full-scan graph deltas to all preceding board layers."""
import argparse,json
from pathlib import Path
import build_array_bridge as base
from build_startup_callback_bridge import once
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent
ARRAY_HEADER=base.array_header
HELPER=r'''
static int robotron_net_inventory(FILE *f,struct ng_vvp *ctx)
{
    int (*inventory)(FILE*)=dlsym(ctx->vvp_handle,"robotron_vvp_net_delta_inventory");
    return inventory ? inventory(f) : -1;
}
static int robotron_net_fault(struct ng_vvp *ctx,int field)
{
    int (*toggle)(int)=dlsym(ctx->vvp_handle,"robotron_vvp_net_toggle");
    return toggle ? toggle(field) : -1;
}
static void robotron_net_reference(struct ng_vvp *ctx)
{
    static struct ng_vvp *owner;
    if(owner && owner!=ctx)exit(3);
    if(owner)return;
    int (*reference)(FILE*)=dlsym(ctx->vvp_handle,"robotron_vvp_net_reference");
    if(!reference || reference(stderr))exit(2);
    owner=ctx;
}
'''
FAULT=r'''
    int net_field=!strcmp(mode,"net-head-corrupt")?0:!strcmp(mode,"net-link-corrupt")?1:!strcmp(mode,"net-tag-corrupt")?2:!strcmp(mode,"net-fun-corrupt")?3:!strcmp(mode,"net-filter-corrupt")?4:!strcmp(mode,"net-foreign-corrupt")?5:-1;
    if(net_field>=0 && ((net_field==0 || net_field==5) ? robotron_start_phase==1 : info->vtime>=5e-6)) {
        if(robotron_net_fault(ctx,net_field)!=1)exit(2);
        char *changed=display_snapshot(ctx,api);
        if(robotron_net_fault(ctx,net_field)!=1)exit(3);
        char *restored=display_snapshot(ctx,api);
        int detected=changed && strcmp(before,changed)!=0;
        int equal=restored && !strcmp(before,restored);
        if(changed)fprintf(stderr,"VB_STAGE changed\n%s",changed);
        if(restored)fprintf(stderr,"VB_STAGE restored\n%s",restored);
        fprintf(stderr,"VB_NET_FAULT field=%d changed=%d restored=%d\n",net_field,detected,equal);
        free(before);free(changed);free(restored);
        exit(detected && equal?2:3);
    }
'''


def net_header(header):
    header=HELPER+'\n'+ARRAY_HEADER(header)
    header=once(header,'robotron_array_inventory(f, ctx) || fprintf(f, "VA_END\\n")',
                'robotron_array_inventory(f, ctx) || robotron_net_inventory(f, ctx) || fprintf(f, "VA_END\\n")')
    modes=''.join(' && strcmp(mode,"net-'+name+'-corrupt")' for name in ('head','link','tag','fun','filter','foreign'))
    header=once(header,'&& strcmp(mode,"array-cache-corrupt"))','&& strcmp(mode,"array-cache-corrupt")'+modes+')')
    header=once(header,'    robotron_operand_reference(ctx);','    robotron_operand_reference(ctx);\n    robotron_net_reference(ctx);')
    return once(header,'    int array_field=',FAULT+'\n    int array_field=')


def build(source,vpi,vpi_header,out):
    try:
        base.array_header=net_header
        base.build(source,vpi,vpi_header,out)
    finally:base.array_header=ARRAY_HEADER
    path=out/'build.json';r=json.loads(path.read_text());r['sources'][str(Path(__file__).resolve())]=sha(Path(__file__))
    r['scope']='All preceding board layers plus full-scan net graph deltas. Actual head/link/tag/binding/foreign-target faults restore before execution. Functor/filter payloads and callbacks remain separate.'
    path.write_text(json.dumps(r,indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('source','vpi','vpi-header','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();build(a.source,a.vpi,a.vpi_header,a.out)
