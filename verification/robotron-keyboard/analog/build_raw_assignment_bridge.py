#!/usr/bin/env python3
"""Add exact scheduled strength payloads to the combined board observer."""
import argparse,json
from pathlib import Path
import build_raw_island_bridge as base
from build_startup_callback_bridge import once
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent
PREVIOUS_HEADER=base.raw_island_header
HELPER=r'''
static int robotron_raw_assignment_inventory(FILE *f,struct ng_vvp *ctx)
{
    int (*inventory)(FILE*)=dlsym(ctx->vvp_handle,"robotron_vvp_assignment_raw_inventory");
    return inventory?inventory(f):-1;
}
static int robotron_raw_assignment_fault(struct ng_vvp *ctx,int operation)
{
    int (*toggle)(unsigned long long,int)=dlsym(ctx->vvp_handle,"robotron_vvp_assignment_raw_toggle");
    char *text=NULL;size_t size=0;FILE *f=open_memstream(&text,&size);
    if(!f || !toggle)return -1;
    int result=robotron_raw_assignment_inventory(f,ctx);if(fclose(f))result=-1;
    if(result){free(text);return -1;}
    unsigned long long selected=0;char *save=NULL;
    for(char *line=strtok_r(text,"\n",&save);line;line=strtok_r(NULL,"\n",&save)) {
        long long slot;char region[32];unsigned long long ordinal,id;void *address,*target;unsigned port,width;
        if(sscanf(line,"VAR_EVENT %lld %31s %llu %llu %p %p %u %u",&slot,region,&ordinal,&id,&address,&target,&port,&width)==8 && (operation!=0 || width)) {selected=id;break;}
    }
    free(text);return selected?toggle(selected,operation):0;
}
'''
FAULT=r'''
    int raw_assignment_op=!strcmp(mode,"raw-assignment-byte-corrupt")?0:!strcmp(mode,"raw-assignment-width-corrupt")?2:!strcmp(mode,"raw-assignment-port-corrupt")?3:-1;
    if(raw_assignment_op>=0 && robotron_start_phase==1) {
        if(robotron_raw_assignment_fault(ctx,raw_assignment_op)!=1)exit(2);
        char *changed=display_snapshot(ctx,api);
        if(robotron_raw_assignment_fault(ctx,raw_assignment_op)!=1)exit(3);
        char *restored=display_snapshot(ctx,api);
        int detected=changed && strcmp(before,changed)!=0;
        int equal=restored && !strcmp(before,restored);
        if(changed)fprintf(stderr,"VB_STAGE changed\n%s",changed);
        if(restored)fprintf(stderr,"VB_STAGE restored\n%s",restored);
        fprintf(stderr,"VB_RAW_ASSIGNMENT_FAULT operation=%d changed=%d restored=%d\n",raw_assignment_op,detected,equal);
        free(before);free(changed);free(restored);
        exit(detected && equal?2:3);
    }
'''

def raw_assignment_header(header):
    header=HELPER+'\n'+PREVIOUS_HEADER(header)
    header=once(header,'robotron_raw_island_inventory(f, ctx) || fprintf(f, "VA_END\\n")','robotron_raw_island_inventory(f, ctx) || robotron_raw_assignment_inventory(f, ctx) || fprintf(f, "VA_END\\n")')
    modes=''.join(' && strcmp(mode,"raw-assignment-'+name+'-corrupt")' for name in ('byte','width','port'))
    header=once(header,'&& strcmp(mode,"raw-island-raw-corrupt"))','&& strcmp(mode,"raw-island-raw-corrupt")'+modes+')')
    return once(header,'    int raw_island_field=',FAULT+'\n    int raw_island_field=')

def build(source,vpi,vpi_header,out):
    try:
        base.raw_island_header=raw_assignment_header
        base.build(source,vpi,vpi_header,out)
    finally:base.raw_island_header=PREVIOUS_HEADER
    path=out/'build.json';r=json.loads(path.read_text());r['sources'][str(Path(__file__).resolve())]=sha(Path(__file__))
    r['scope']='Preceding combined raw-island observer plus complete queued/executing strength assignment payloads, lifetime and target/port fields. Startup byte/width/port faults restore before termination. Native collision coverage remains separate; operational cost and qualification require completed board controls.'
    path.write_text(json.dumps(r,indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('source','vpi','vpi-header','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();build(a.source,a.vpi,a.vpi_header,a.out)
