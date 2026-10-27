#!/usr/bin/env python3
"""Add exact raw island differences to the combined board observer."""
import argparse,json
from pathlib import Path
import build_resolver_bridge as base
from build_startup_callback_bridge import once
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent
PREVIOUS_HEADER=base.resolver_header
HELPER=r'''
static int robotron_raw_island_inventory(FILE *f,struct ng_vvp *ctx)
{
    int (*inventory)(FILE*)=dlsym(ctx->vvp_handle,"robotron_vvp_island_raw_delta_inventory");
    return inventory ? inventory(f) : -1;
}
static int robotron_raw_island_fault(struct ng_vvp *ctx,int field)
{
    int (*toggle)(int,int)=dlsym(ctx->vvp_handle,"robotron_vvp_island_raw_toggle");
    int vector=field==1?1:0;int operation=field==0?0:field==1?2:1;
    return toggle?toggle(vector,operation):-1;
}
static void robotron_raw_island_reference(struct ng_vvp *ctx)
{
    static struct ng_vvp *owner;
    if(owner && owner!=ctx)exit(3);
    if(owner)return;
    int (*reference)(FILE*)=dlsym(ctx->vvp_handle,"robotron_vvp_island_raw_reference");
    if(!reference || reference(stderr))exit(2);
    owner=ctx;
}
'''
FAULT=r'''
    int raw_island_field=!strcmp(mode,"raw-island-cache-corrupt")?0:!strcmp(mode,"raw-island-width-corrupt")?1:!strcmp(mode,"raw-island-raw-corrupt")?2:-1;
    if(raw_island_field>=0 && (raw_island_field==0 ? robotron_start_phase==1 : info->vtime>=5e-6)) {
        if(robotron_raw_island_fault(ctx,raw_island_field)!=1)exit(2);
        char *changed=display_snapshot(ctx,api);
        if(robotron_raw_island_fault(ctx,raw_island_field)!=1)exit(3);
        char *restored=display_snapshot(ctx,api);
        int detected=changed && strcmp(before,changed)!=0;
        int equal=restored && !strcmp(before,restored);
        if(changed)fprintf(stderr,"VB_STAGE changed\n%s",changed);
        if(restored)fprintf(stderr,"VB_STAGE restored\n%s",restored);
        fprintf(stderr,"VB_RAW_ISLAND_FAULT field=%d changed=%d restored=%d\n",raw_island_field,detected,equal);
        free(before);free(changed);free(restored);
        exit(detected && equal?2:3);
    }
'''


def raw_island_header(header):
    header=HELPER+'\n'+PREVIOUS_HEADER(header)
    header=once(header,'robotron_resolver_inventory(f, ctx) || fprintf(f, "VA_END\\n")',
                'robotron_resolver_inventory(f, ctx) || robotron_raw_island_inventory(f, ctx) || fprintf(f, "VA_END\\n")')
    modes=''.join(' && strcmp(mode,"raw-island-'+name+'-corrupt")' for name in ('cache','width','raw'))
    header=once(header,'&& strcmp(mode,"resolver-raw-corrupt"))','&& strcmp(mode,"resolver-raw-corrupt")'+modes+')')
    header=once(header,'    robotron_resolver_reference(ctx);','    robotron_resolver_reference(ctx);\n    robotron_raw_island_reference(ctx);')
    return once(header,'    int resolver_field=',FAULT+'\n    int resolver_field=')


def build(source,vpi,vpi_header,out):
    try:
        base.resolver_header=raw_island_header
        base.build(source,vpi,vpi_header,out)
    finally:base.resolver_header=PREVIOUS_HEADER
    path=out/'build.json';r=json.loads(path.read_text());r['sources'][str(Path(__file__).resolve())]=sha(Path(__file__))
    r['scope']='All preceding layers plus full-scan raw island differences and restored input-byte/output-width/raw-collision faults. Legacy mesh/filter/queue checks remain present. Scheduled vector-8 payloads remain separate.'
    path.write_text(json.dumps(r,indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('source','vpi','vpi-header','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();build(a.source,a.vpi,a.vpi_header,a.out)
