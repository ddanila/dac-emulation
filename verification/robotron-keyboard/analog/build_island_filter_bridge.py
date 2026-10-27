#!/usr/bin/env python3
"""Add island wire-filter state to the combined board observer."""
import argparse,json
from pathlib import Path
import build_island_bridge as base
from build_startup_callback_bridge import once
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent
ISLAND_HEADER=base.island_header
HELPER=r'''
static int robotron_filter_inventory(FILE *f,struct ng_vvp *ctx)
{
    int (*inventory)(FILE*)=dlsym(ctx->vvp_handle,"robotron_vvp_island_filter_inventory");
    return inventory?inventory(f):-1;
}
static int robotron_filter_fault(struct ng_vvp *ctx,int field)
{
    int (*toggle)(int)=dlsym(ctx->vvp_handle,"robotron_vvp_island_filter_toggle");
    return toggle?toggle(field):-1;
}
'''
FAULT=r'''
    int filter_field=-1;
    const char *filter_modes[]={"filter-init-corrupt","filter-driven-corrupt","filter-propagate-corrupt","filter-strength-corrupt"};
    const int filter_fields[]={0,1,4,6};
    for(int i=0;i<4;i++)if(!strcmp(mode,filter_modes[i]))filter_field=filter_fields[i];
    if(filter_field>=0 && (filter_field==6 ? info->vtime>=5e-6 : robotron_start_phase==1)) {
        if(robotron_filter_fault(ctx,filter_field)!=1)exit(2);
        char *changed=display_snapshot(ctx,api);
        if(robotron_filter_fault(ctx,filter_field)!=1)exit(3);
        char *restored=display_snapshot(ctx,api);
        int detected=changed && strcmp(before,changed)!=0;
        int equal=restored && !strcmp(before,restored);
        if(changed)fprintf(stderr,"VB_STAGE changed\n%s",changed);
        if(restored)fprintf(stderr,"VB_STAGE restored\n%s",restored);
        fprintf(stderr,"VB_FILTER_FAULT field=%d changed=%d restored=%d\n",filter_field,detected,equal);
        free(before);free(changed);free(restored);
        exit(detected && equal?2:3);
    }
'''


def filter_header(header):
    header=HELPER+'\n'+ISLAND_HEADER(header)
    header=once(header,'robotron_island_inventory(f, ctx) || fprintf(f, "VA_END\\n")',
                'robotron_island_inventory(f, ctx) || robotron_filter_inventory(f, ctx) || fprintf(f, "VA_END\\n")')
    modes=''.join(' && strcmp(mode,"filter-'+mode+'-corrupt")' for mode in ('init','driven','propagate','strength'))
    header=once(header,'&& strcmp(mode,"island-queue-corrupt"))','&& strcmp(mode,"island-queue-corrupt")'+modes+')')
    return once(header,'    int island_field=',FAULT+'\n    int island_field=')


def build(source,vpi,vpi_header,out):
    try:
        base.island_header=filter_header
        base.build(source,vpi,vpi_header,out)
    finally:base.island_header=ISLAND_HEADER
    path=out/'build.json';r=json.loads(path.read_text());r['sources'][str(Path(__file__).resolve())]=sha(Path(__file__))
    r['scope']='Combined island/queue board observer with island vec8 filters. Restored initialization, driven-value, propagation and strength faults. Active forced masks/links are covered by separate fixture controls; callback/fanout referents and thread state remain open.'
    path.write_text(json.dumps(r,indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('source','vpi','vpi-header','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();build(a.source,a.vpi,a.vpi_header,a.out)
