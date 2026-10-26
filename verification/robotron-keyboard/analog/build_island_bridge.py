#!/usr/bin/env python3
"""Add live islands and queued wrapper relationships to the combined observer."""
import argparse,json
from pathlib import Path
import build_primitive_bridge as base
from build_startup_callback_bridge import once
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent
PRIMITIVE_HEADER=base.primitive_header
HELPER=r'''
static int robotron_island_inventory(FILE *f,struct ng_vvp *ctx)
{
    int (*inventory)(FILE*)=dlsym(ctx->vvp_handle,"robotron_vvp_island_inventory");
    int (*queue)(FILE*)=dlsym(ctx->vvp_handle,"robotron_vvp_island_queue_inventory");
    return inventory && queue ? (inventory(f) || queue(f)) : -1;
}
static int robotron_island_fault(struct ng_vvp *ctx,int field)
{
    int (*toggle)(int)=dlsym(ctx->vvp_handle,"robotron_vvp_island_toggle");
    int (*queue)(void)=dlsym(ctx->vvp_handle,"robotron_vvp_island_queue_toggle");
    return field==6 ? (queue?queue():-1) : (toggle?toggle(field):-1);
}
'''
FAULT=r'''
    int island_field=-1;
    const char *island_modes[]={"island-flag-corrupt","island-input-corrupt","island-output-corrupt",
        "island-strength-corrupt","island-enable-corrupt","island-mesh-corrupt","island-queue-corrupt"};
    for(int i=0;i<7;i++)if(!strcmp(mode,island_modes[i]))island_field=i;
    if(island_field>=0 && (island_field==2 ? info->vtime>=5e-6 : robotron_start_phase==1)) {
        if(robotron_island_fault(ctx,island_field)!=1)exit(2);
        char *changed=display_snapshot(ctx,api);
        if(robotron_island_fault(ctx,island_field)!=1)exit(3);
        char *restored=display_snapshot(ctx,api);
        int detected=changed && strcmp(before,changed)!=0;
        int equal=restored && !strcmp(before,restored);
        if(changed)fprintf(stderr,"VB_STAGE changed\n%s",changed);
        if(restored)fprintf(stderr,"VB_STAGE restored\n%s",restored);
        fprintf(stderr,"VB_ISLAND_FAULT field=%d changed=%d restored=%d\n",island_field,detected,equal);
        free(before);free(changed);free(restored);
        exit(detected && equal?2:3);
    }
'''


def island_header(header):
    header=HELPER+'\n'+PRIMITIVE_HEADER(header)
    header=once(header,'robotron_primitive_inventory(f, ctx) || fprintf(f, "VA_END\\n")',
                'robotron_primitive_inventory(f, ctx) || robotron_island_inventory(f, ctx) || fprintf(f, "VA_END\\n")')
    modes=''.join(' && strcmp(mode,"island-'+mode+'-corrupt")' for mode in ('flag','input','output','strength','enable','mesh','queue'))
    header=once(header,'&& strcmp(mode,"primitive-part-base-corrupt"))','&& strcmp(mode,"primitive-part-base-corrupt")'+modes+')')
    return once(header,'    int primitive_kind=',FAULT+'\n    int primitive_kind=')


def build(source,vpi,vpi_header,out):
    try:
        base.primitive_header=island_header
        base.build(source,vpi,vpi_header,out)
    finally:base.primitive_header=PRIMITIVE_HEADER
    path=out/'build.json';r=json.loads(path.read_text());r['sources'][str(Path(__file__).resolve())]=sha(Path(__file__))
    r['scope']='Combined board observer with persistent islands and queued wrapper relationships. Restored flag/cache/strength/branch/mesh/queue faults precede continuation. Force/filter referents, threads and general rollback remain open.'
    path.write_text(json.dumps(r,indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('source','vpi','vpi-header','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();build(a.source,a.vpi,a.vpi_header,a.out)
