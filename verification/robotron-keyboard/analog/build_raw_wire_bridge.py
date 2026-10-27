#!/usr/bin/env python3
"""Add exact raw wire-cache payloads to every preceding board layer."""
import argparse,json
from pathlib import Path
import build_reduction_bridge as base
from build_startup_callback_bridge import once
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent
REDUCTION_HEADER=base.reduction_header
HELPER=r'''
static int robotron_raw_wire_inventory(FILE *f,struct ng_vvp *ctx)
{
    int (*inventory)(FILE*)=dlsym(ctx->vvp_handle,"robotron_vvp_wire_raw_delta_inventory");
    return inventory ? inventory(f) : -1;
}
static int robotron_raw_wire_fault(struct ng_vvp *ctx,int field)
{
    static unsigned long long saved;
    int (*toggle)(unsigned long long,int)=dlsym(ctx->vvp_handle,"robotron_vvp_wire_raw_toggle");
    int (*inventory)(FILE*)=dlsym(ctx->vvp_handle,"robotron_vvp_wire_raw_inventory");
    if(!toggle || !inventory)return -1;
    if(saved){int result=toggle(saved,0);if(result==1)saved=0;return result;}
    char *text=NULL;size_t size=0;FILE *f=open_memstream(&text,&size);if(!f)return -1;
    int result=inventory(f);if(fclose(f))result=-1;
    if(result){free(text);return -1;}
    char *cursor=text,*line;
    while((line=strsep(&cursor,"\n"))!=NULL){
        unsigned long long id;
        if(sscanf(line,"VWB_FILTER %llu",&id)!=1)continue;
        result=toggle(id,0);
        if(result){if(result==1)saved=id;free(text);return result;}
    }
    free(text);return 0;
}
static void robotron_raw_wire_reference(struct ng_vvp *ctx)
{
    static struct ng_vvp *owner;
    if(owner && owner!=ctx)exit(3);
    if(owner)return;
    int (*reference)(FILE*)=dlsym(ctx->vvp_handle,"robotron_vvp_wire_raw_reference");
    if(!reference || reference(stderr))exit(2);
    owner=ctx;
}
'''
FAULT=r'''
    int raw_wire_field=!strcmp(mode,"raw-wire-corrupt")?0:!strcmp(mode,"raw-wire-delayed-corrupt")?1:-1;
    if(raw_wire_field>=0 && (raw_wire_field==0 ? robotron_start_phase==1 : info->vtime>=5e-6)) {
        if(robotron_raw_wire_fault(ctx,raw_wire_field)!=1)exit(2);
        char *changed=display_snapshot(ctx,api);
        if(robotron_raw_wire_fault(ctx,raw_wire_field)!=1)exit(3);
        char *restored=display_snapshot(ctx,api);
        int detected=changed && strcmp(before,changed)!=0;
        int equal=restored && !strcmp(before,restored);
        if(changed)fprintf(stderr,"VB_STAGE changed\n%s",changed);
        if(restored)fprintf(stderr,"VB_STAGE restored\n%s",restored);
        fprintf(stderr,"VB_RAW_WIRE_FAULT delayed=%d changed=%d restored=%d\n",raw_wire_field,detected,equal);
        free(before);free(changed);free(restored);
        exit(detected && equal?2:3);
    }
'''


def raw_wire_header(header):
    header=HELPER+'\n'+REDUCTION_HEADER(header)
    header=once(header,'robotron_reduction_inventory(f, ctx) || fprintf(f, "VA_END\\n")',
                'robotron_reduction_inventory(f, ctx) || robotron_raw_wire_inventory(f, ctx) || fprintf(f, "VA_END\\n")')
    modes=' && strcmp(mode,"raw-wire-corrupt") && strcmp(mode,"raw-wire-delayed-corrupt")'
    header=once(header,'&& strcmp(mode,"reduction-size-corrupt"))','&& strcmp(mode,"reduction-size-corrupt")'+modes+')')
    header=once(header,'    robotron_reduction_reference(ctx);','    robotron_reduction_reference(ctx);\n    robotron_raw_wire_reference(ctx);')
    return once(header,'    int reduction_field=',FAULT+'\n    int reduction_field=')



def build(source,vpi,vpi_header,out):
    try:
        base.reduction_header=raw_wire_header
        base.build(source,vpi,vpi_header,out)
    finally:base.reduction_header=REDUCTION_HEADER
    path=out/'build.json';r=json.loads(path.read_text());r['sources'][str(Path(__file__).resolve())]=sha(Path(__file__))
    r['scope']='All preceding layers plus exact raw wire cache differences and restored hidden-byte faults at initial/later boundaries. Legacy triplet views must remain unchanged by these faults. Other strength payloads and general rollback remain separate.'
    path.write_text(json.dumps(r,indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('source','vpi','vpi-header','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();build(a.source,a.vpi,a.vpi_header,a.out)
