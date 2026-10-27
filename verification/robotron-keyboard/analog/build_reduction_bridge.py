#!/usr/bin/env python3
"""Add lossless static reduction payloads to every preceding board layer."""
import argparse,json
from pathlib import Path
import build_arithmetic_bridge as base
from build_startup_callback_bridge import once
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent
ARITHMETIC_HEADER=base.arithmetic_header
HELPER=r'''
static int robotron_reduction_inventory(FILE *f,struct ng_vvp *ctx)
{
    int (*inventory)(FILE*)=dlsym(ctx->vvp_handle,"robotron_vvp_reduction_delta_inventory");
    return inventory ? inventory(f) : -1;
}
static int robotron_reduction_fault(struct ng_vvp *ctx,int field)
{
    static unsigned long long saved;
    int (*toggle)(unsigned long long,int)=dlsym(ctx->vvp_handle,"robotron_vvp_reduction_toggle");
    int (*inventory)(FILE*)=dlsym(ctx->vvp_handle,"robotron_vvp_reduction_inventory");
    if(!toggle || !inventory)return -1;
    if(saved){int result=toggle(saved,field);if(result==1)saved=0;return result;}
    char *text=NULL;size_t size=0;FILE *f=open_memstream(&text,&size);if(!f)return -1;
    int result=inventory(f);if(fclose(f))result=-1;
    if(result){free(text);return -1;}
    char *cursor=text,*line;
    while((line=strsep(&cursor,"\n"))!=NULL){
        unsigned long long id;int kind;
        if(sscanf(line,"VRD_NODE %llu %*s %*s %d",&id,&kind)!=2)continue;
        result=toggle(id,field);
        if(result){if(result==1)saved=id;free(text);return result;}
    }
    free(text);return 0;
}
static void robotron_reduction_reference(struct ng_vvp *ctx)
{
    static struct ng_vvp *owner;
    if(owner && owner!=ctx)exit(3);
    if(owner)return;
    int (*reference)(FILE*)=dlsym(ctx->vvp_handle,"robotron_vvp_reduction_reference");
    if(!reference || reference(stderr))exit(2);
    owner=ctx;
}
'''
FAULT=r'''
    int reduction_field=!strcmp(mode,"reduction-bit-corrupt")?0:!strcmp(mode,"reduction-size-corrupt")?1:-1;
    if(reduction_field>=0 && (reduction_field==0 ? robotron_start_phase==1 : info->vtime>=5e-6)) {
        if(robotron_reduction_fault(ctx,reduction_field)!=1)exit(2);
        char *changed=display_snapshot(ctx,api);
        if(robotron_reduction_fault(ctx,reduction_field)!=1)exit(3);
        char *restored=display_snapshot(ctx,api);
        int detected=changed && strcmp(before,changed)!=0;
        int equal=restored && !strcmp(before,restored);
        if(changed)fprintf(stderr,"VB_STAGE changed\n%s",changed);
        if(restored)fprintf(stderr,"VB_STAGE restored\n%s",restored);
        fprintf(stderr,"VB_REDUCTION_FAULT field=%d changed=%d restored=%d\n",reduction_field,detected,equal);
        free(before);free(changed);free(restored);
        exit(detected && equal?2:3);
    }
'''


def reduction_header(header):
    header=HELPER+'\n'+ARITHMETIC_HEADER(header)
    header=once(header,'robotron_arithmetic_inventory(f, ctx) || fprintf(f, "VA_END\\n")',
                'robotron_arithmetic_inventory(f, ctx) || robotron_reduction_inventory(f, ctx) || fprintf(f, "VA_END\\n")')
    modes=''.join(' && strcmp(mode,"reduction-'+name+'-corrupt")' for name in ('bit','size'))
    header=once(header,'&& strcmp(mode,"arithmetic-width-corrupt"))','&& strcmp(mode,"arithmetic-width-corrupt")'+modes+')')
    header=once(header,'    robotron_arithmetic_reference(ctx);','    robotron_arithmetic_reference(ctx);\n    robotron_reduction_reference(ctx);')
    return once(header,'    int arithmetic_field=',FAULT+'\n    int arithmetic_field=')


def build(source,vpi,vpi_header,out):
    try:
        base.arithmetic_header=reduction_header
        base.build(source,vpi,vpi_header,out)
    finally:base.arithmetic_header=ARITHMETIC_HEADER
    path=out/'build.json';r=json.loads(path.read_text());r['sources'][str(Path(__file__).resolve())]=sha(Path(__file__))
    r['scope']='All preceding board layers plus full-scan reduction differences, native class/graph bindings and restored bit/vector-size faults. Other functor payloads and callbacks remain separate.'
    path.write_text(json.dumps(r,indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('source','vpi','vpi-header','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();build(a.source,a.vpi,a.vpi_header,a.out)
