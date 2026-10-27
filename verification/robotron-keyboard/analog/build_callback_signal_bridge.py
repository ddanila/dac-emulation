#!/usr/bin/env python3
"""Add typed port-signal metadata and callback-owner links to combined observation."""
import argparse,json
from pathlib import Path
import build_callback_list_bridge as base
from build_startup_callback_bridge import once
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent
PREVIOUS_HEADER=base.callback_header
PROTOTYPES='static void robotron_typed_signal_reference(struct ng_vvp*);\nstatic int robotron_typed_signal_inventory(FILE*,struct ng_vvp*);\n'
HELPER=r'''
static struct ng_vvp*robotron_typed_signal_context;
static struct robotron_typed_signal_binding {void*handle;unsigned long long id;} *robotron_typed_signal_bindings;
static size_t robotron_typed_signal_count;
static void robotron_typed_signal_reference(struct ng_vvp*ctx)
{
    if(robotron_typed_signal_context){if(robotron_typed_signal_context!=ctx)exit(3);return;}
    if(ctx!=robotron_ports_context || ctx->ports!=robotron_ports_base)exit(2);
    unsigned long long(*admit)(void*)=dlsym(ctx->vvp_handle,"robotron_vvp_signal_handle_admit");
    if(!admit)exit(2);
    robotron_typed_signal_count=(size_t)ctx->ins+ctx->outs+ctx->inouts;
    robotron_typed_signal_bindings=calloc(robotron_typed_signal_count,sizeof(*robotron_typed_signal_bindings));
    if(!robotron_typed_signal_bindings)exit(2);
    fprintf(stderr,"VHB_BEGIN 1 %zu\n",robotron_typed_signal_count);
    for(size_t i=0;i<robotron_typed_signal_count;++i){
        struct ngvp_port*p=ctx->ports+i;
        if(p->ctx!=ctx || !p->handle)exit(2);
        unsigned long long id=admit(p->handle);if(!id)exit(2);
        robotron_typed_signal_bindings[i].handle=p->handle;robotron_typed_signal_bindings[i].id=id;
        fprintf(stderr,"VHB_LINK %zu %llu %p %p\n",i,id,(void*)p,(void*)p->handle);
    }
    fprintf(stderr,"VHB_END\n");if(ferror(stderr))exit(2);robotron_typed_signal_context=ctx;
}
static int robotron_typed_signal_inventory(FILE*f,struct ng_vvp*ctx)
{
    if(!ctx || robotron_typed_signal_context!=ctx || ctx!=robotron_ports_context ||
       ctx->ports!=robotron_ports_base || robotron_typed_signal_count!=(size_t)ctx->ins+ctx->outs+ctx->inouts)return -1;
    for(size_t i=0;i<robotron_typed_signal_count;++i)
        if(ctx->ports[i].ctx!=ctx || ctx->ports[i].handle!=robotron_typed_signal_bindings[i].handle)return -1;
    int(*handles)(FILE*)=dlsym(ctx->vvp_handle,"robotron_vvp_signal_handle_inventory");
    int(*links)(FILE*)=dlsym(ctx->vvp_handle,"robotron_vvp_callback_signal_inventory");
    return !handles||!links||handles(f)||links(f)?-1:0;
}
'''


def signal_header(header):
    header=PROTOTYPES+PREVIOUS_HEADER(header)+'\n'+HELPER
    header=once(header,'robotron_callback_inventory(f, ctx) || fprintf(f, "VA_END\\n")','robotron_callback_inventory(f, ctx) || robotron_typed_signal_inventory(f, ctx) || fprintf(f, "VA_END\\n")')
    return once(header,'    robotron_callback_reference(ctx);','    robotron_callback_reference(ctx);\n    robotron_typed_signal_reference(ctx);')


def build(source,vpi,vpi_header,out):
    try:
        base.callback_header=signal_header;base.build(source,vpi,vpi_header,out)
    finally:base.callback_header=PREVIOUS_HEADER
    p=out/'build.json';r=json.loads(p.read_text());r['sources'][str(Path(__file__).resolve())]=sha(Path(__file__))
    r['scope']='All preceding combined callback-list layers plus explicitly admitted typed port signals and complete callback-owner/node/filter links. Binding handoff follows port initialization; each snapshot checks original port handles and emits native metadata/linkage. Existing callback startup faults restore complete state. Typed metadata-specific combined faults and operational qualification remain separate.'
    p.write_text(json.dumps(r,indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('source','vpi','vpi-header','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();build(a.source,a.vpi,a.vpi_header,a.out)
