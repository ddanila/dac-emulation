#!/usr/bin/env python3
"""Integrate compact callback lists after all preceding board observer layers."""
import argparse,json
from pathlib import Path
import build_raw_assignment_bridge as base
from build_startup_callback_bridge import once
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent
PREVIOUS_HEADER=base.raw_assignment_header
PROTOTYPES='static void robotron_callback_reference(struct ng_vvp*);\nstatic int robotron_callback_inventory(FILE*,struct ng_vvp*);\nstatic char* robotron_callback_text(struct ng_vvp*);\n'
HELPER=r'''
static struct ng_vvp *robotron_callback_context;
static int robotron_callback_bindings(struct ng_vvp *ctx)
{
    if(!ctx || ctx!=robotron_ports_context || ctx->ports!=robotron_ports_base ||
       !robotron_outputs || robotron_outputs_count!=(size_t)ctx->outs+ctx->inouts)return -1;
    for(size_t i=0;i<robotron_outputs_count;i++){
        const struct robotron_output_identity*r=robotron_outputs+i;
        struct ngvp_port*p=ctx->ports+ctx->ins+i;
        if(r->port!=p || p->ctx!=ctx || p->handle!=r->signal ||
           robotron_output_lookup(r->callback,r->function,(char*)p,r->signal)!=r->lifetime)return -1;
    }
    return 0;
}
static void robotron_callback_reference(struct ng_vvp *ctx)
{
    if(robotron_callback_context){if(robotron_callback_context!=ctx)exit(3);return;}
    if(robotron_callback_bindings(ctx))exit(2);
    output_lookup_fn admit=dlsym(ctx->vvp_handle,"robotron_vvp_callback_list_admit");
    int(*reference)(FILE*)=dlsym(ctx->vvp_handle,"robotron_vvp_callback_list_reference");
    if(!admit||!reference)exit(2);
    for(size_t i=0;i<robotron_outputs_count;i++){
        const struct robotron_output_identity*r=robotron_outputs+i;
        if(admit(r->callback,r->function,(char*)r->port,r->signal)!=r->lifetime)exit(2);
    }
    fprintf(stderr,"VLB_BEGIN 1 %zu\n",robotron_outputs_count);
    for(size_t i=0;i<robotron_outputs_count;i++){
        const struct robotron_output_identity*r=robotron_outputs+i;
        fprintf(stderr,"VLB_LINK %zu %llu %p %p %p %p\n",(size_t)ctx->ins+i,r->lifetime,(void*)r->port,(void*)r->callback,(void*)r->signal,(void*)r->function);
    }
    fprintf(stderr,"VLB_END\n");
    if(ferror(stderr)||reference(stderr))exit(2);
    robotron_callback_context=ctx;
}
static int robotron_callback_inventory(FILE*f,struct ng_vvp*ctx)
{
    if(robotron_callback_context!=ctx || robotron_callback_bindings(ctx))return -1;
    int(*delta)(FILE*)=dlsym(ctx->vvp_handle,"robotron_vvp_callback_list_delta_inventory");
    return delta?delta(f):-1;
}
static char* robotron_callback_text(struct ng_vvp*ctx)
{
    char*text=NULL;size_t size=0;FILE*f=open_memstream(&text,&size);if(!f)return NULL;
    int result=robotron_callback_inventory(f,ctx);if(fclose(f))result=-1;
    if(result){free(text);return NULL;}return text;
}
'''
FAULT=r'''
    int callback_list_field=!strcmp(mode,"callback-list-user-corrupt")?0:!strcmp(mode,"callback-list-object-corrupt")?1:!strcmp(mode,"callback-list-function-corrupt")?2:!strcmp(mode,"callback-list-link-corrupt")?3:-1;
    if(callback_list_field>=0 && robotron_start_phase==1){
        if(robotron_output_fault(callback_list_field)!=1)exit(2);
        char*direct=robotron_callback_text(ctx);
        char*changed=display_snapshot(ctx,api);
        if(robotron_output_fault(callback_list_field)!=1)exit(3);
        char*restored=display_snapshot(ctx,api);
        int direct_rejected=direct==NULL,rejected=changed==NULL,equal=restored&&!strcmp(before,restored);
        if(restored)fprintf(stderr,"VB_STAGE restored\n%s",restored);
        fprintf(stderr,"VB_CALLBACK_LIST_FAULT field=%d direct_rejected=%d rejected=%d restored=%d\n",callback_list_field,direct_rejected,rejected,equal);
        free(before);free(direct);free(changed);free(restored);
        exit(direct_rejected&&rejected&&equal?2:3);
    }
'''


def callback_header(header):
    header=PROTOTYPES+PREVIOUS_HEADER(header)+'\n'+HELPER
    header=once(header,'robotron_raw_assignment_inventory(f, ctx) || fprintf(f, "VA_END\\n")','robotron_raw_assignment_inventory(f, ctx) || robotron_callback_inventory(f, ctx) || fprintf(f, "VA_END\\n")')
    header=once(header,'    robotron_raw_island_reference(ctx);','    robotron_raw_island_reference(ctx);\n    robotron_callback_reference(ctx);')
    modes=''.join(' && strcmp(mode,"callback-list-'+name+'-corrupt")' for name in ('user','object','function','link'))
    header=once(header,'&& strcmp(mode,"raw-assignment-port-corrupt"))','&& strcmp(mode,"raw-assignment-port-corrupt")'+modes+')')
    return once(header,'    int raw_assignment_op=',FAULT+'\n    int raw_assignment_op=')


def build(source,vpi,vpi_header,out):
    try:
        base.raw_assignment_header=callback_header;base.build(source,vpi,vpi_header,out)
    finally:base.raw_assignment_header=PREVIOUS_HEADER
    p=out/'build.json';r=json.loads(p.read_text());r['sources'][str(Path(__file__).resolve())]=sha(Path(__file__))
    r['scope']='Combined raw-assignment and preceding observers plus complete compact callback-owner lists. Explicit admission follows initialized bridge bindings; every snapshot revalidates registered port/signal/function/lifetime identities. User/object/function/link faults must independently refuse callback inventory and combined inventory, restoring before termination. Operational qualification remains separate.'
    p.write_text(json.dumps(r,indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('source','vpi','vpi-header','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();build(a.source,a.vpi,a.vpi_header,a.out)
