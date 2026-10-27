#!/usr/bin/env python3
"""Add lossless static resolver payloads to every preceding board layer."""
import argparse,json
from pathlib import Path
import build_concat_bridge as base
from build_startup_callback_bridge import once
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent
PREVIOUS_HEADER=base.concat_header
HELPER=r'''
static int robotron_resolver_inventory(FILE *f,struct ng_vvp *ctx)
{
    int (*inventory)(FILE*)=dlsym(ctx->vvp_handle,"robotron_vvp_resolver_delta_inventory");
    return inventory ? inventory(f) : -1;
}
static int robotron_resolver_fault(struct ng_vvp *ctx,int field)
{
    static unsigned long long saved;static unsigned saved_index;
    int (*toggle)(unsigned long long,int,unsigned)=dlsym(ctx->vvp_handle,"robotron_vvp_resolver_toggle");
    int (*inventory)(FILE*)=dlsym(ctx->vvp_handle,"robotron_vvp_resolver_inventory");
    if(!toggle || !inventory)return -1;
    if(saved){int result=toggle(saved,field,saved_index);if(result==1)saved=0;return result;}
    char *text=NULL;size_t size=0;FILE *f=open_memstream(&text,&size);if(!f)return -1;
    int result=inventory(f);if(fclose(f))result=-1;
    if(result){free(text);return -1;}
    char *cursor=text,*line;
    while((line=strsep(&cursor,"\n"))!=NULL){
        unsigned long long id;unsigned slots;
        if(sscanf(line,"VRS_NODE %llu %*s %*s %*u %*u %*s %*s %*s %u",&id,&slots)!=2)continue;
        for(unsigned index=0;index<((field==0 || field==6)?slots:1);index++){
            result=toggle(id,field,index);
            if(result){if(result==1){saved=id;saved_index=index;}free(text);return result;}
        }
    }
    free(text);return 0;
}
static void robotron_resolver_reference(struct ng_vvp *ctx)
{
    static struct ng_vvp *owner;
    if(owner && owner!=ctx)exit(3);
    if(owner)return;
    int (*reference)(FILE*)=dlsym(ctx->vvp_handle,"robotron_vvp_resolver_reference");
    if(!reference || reference(stderr))exit(2);
    owner=ctx;
}
'''
FAULT=r'''
    int resolver_field=!strcmp(mode,"resolver-cache-corrupt")?0:!strcmp(mode,"resolver-allocation-corrupt")?5:!strcmp(mode,"resolver-raw-corrupt")?6:-1;
    if(resolver_field>=0 && (resolver_field==0 ? robotron_start_phase==1 : info->vtime>=5e-6)) {
        if(robotron_resolver_fault(ctx,resolver_field)!=1)exit(2);
        char *changed=display_snapshot(ctx,api);
        if(robotron_resolver_fault(ctx,resolver_field)!=1)exit(3);
        char *restored=display_snapshot(ctx,api);
        int detected=changed && strcmp(before,changed)!=0;
        int equal=restored && !strcmp(before,restored);
        if(changed)fprintf(stderr,"VB_STAGE changed\n%s",changed);
        if(restored)fprintf(stderr,"VB_STAGE restored\n%s",restored);
        fprintf(stderr,"VB_RESOLVER_FAULT field=%d changed=%d restored=%d\n",resolver_field,detected,equal);
        free(before);free(changed);free(restored);
        exit(detected && equal?2:3);
    }
'''


def resolver_header(header):
    header=HELPER+'\n'+PREVIOUS_HEADER(header)
    header=once(header,'robotron_concat_inventory(f, ctx) || fprintf(f, "VA_END\\n")',
                'robotron_concat_inventory(f, ctx) || robotron_resolver_inventory(f, ctx) || fprintf(f, "VA_END\\n")')
    modes=''.join(' && strcmp(mode,"resolver-'+name+'-corrupt")' for name in ('cache','allocation','raw'))
    header=once(header,'&& strcmp(mode,"concat-raw-corrupt"))','&& strcmp(mode,"concat-raw-corrupt")'+modes+')')
    header=once(header,'    robotron_concat_reference(ctx);','    robotron_concat_reference(ctx);\n    robotron_resolver_reference(ctx);')
    return once(header,'    int concat_field=',FAULT+'\n    int concat_field=')


def build(source,vpi,vpi_header,out):
    try:
        base.concat_header=resolver_header
        base.build(source,vpi,vpi_header,out)
    finally:base.concat_header=PREVIOUS_HEADER
    path=out/'build.json';r=json.loads(path.read_text());r['sources'][str(Path(__file__).resolve())]=sha(Path(__file__))
    r['scope']='All preceding board layers plus full-scan resolver differences, native class/graph bindings and restored cache/allocation-pointer/raw-collision faults. Other functor payloads and callbacks remain separate.'
    path.write_text(json.dumps(r,indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('source','vpi','vpi-header','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();build(a.source,a.vpi,a.vpi_header,a.out)
