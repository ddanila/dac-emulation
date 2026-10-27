#!/usr/bin/env python3
"""Add initialized live threads and queued event binding to the board observer."""
import argparse,json
from pathlib import Path
import build_island_filter_bridge as base
from build_startup_callback_bridge import once
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent
FILTER_HEADER=base.filter_header
HELPER=r'''
static int robotron_thread_inventory(FILE *f,struct ng_vvp *ctx)
{
    int (*inventory)(FILE*)=dlsym(ctx->vvp_handle,"robotron_vvp_thread_compact_inventory");
    int (*queue)(FILE*)=dlsym(ctx->vvp_handle,"robotron_vvp_thread_queue_inventory");
    return inventory && queue ? (inventory(f) || queue(f)) : -1;
}
static int robotron_thread_fault(struct ng_vvp *ctx,int field)
{
    int (*toggle)(int)=dlsym(ctx->vvp_handle,"robotron_vvp_thread_toggle");
    int (*queue)(void)=dlsym(ctx->vvp_handle,"robotron_vvp_thread_queue_toggle");
    return field==8 ? (queue?queue():-1) : (toggle?toggle(field):-1);
}
'''
FAULT=r'''
    int thread_field=-1;
    const char *thread_modes[]={"thread-schedule-corrupt","thread-flag-corrupt","thread-word-corrupt",
                               "thread-pc-corrupt","thread-wait-corrupt","thread-queue-corrupt"};
    const int thread_fields[]={0,1,2,3,4,8};
    for(int i=0;i<6;i++)if(!strcmp(mode,thread_modes[i]))thread_field=thread_fields[i];
    if(thread_field>=0 && (thread_field==2 ? info->vtime>=5e-6 : robotron_start_phase==1)) {
        if(robotron_thread_fault(ctx,thread_field)!=1)exit(2);
        char *changed=display_snapshot(ctx,api);
        if(robotron_thread_fault(ctx,thread_field)!=1)exit(3);
        char *restored=display_snapshot(ctx,api);
        int detected=changed && strcmp(before,changed)!=0;
        int equal=restored && !strcmp(before,restored);
        if(changed)fprintf(stderr,"VB_STAGE changed\n%s",changed);
        if(restored)fprintf(stderr,"VB_STAGE restored\n%s",restored);
        fprintf(stderr,"VB_THREAD_FAULT field=%d changed=%d restored=%d\n",thread_field,detected,equal);
        free(before);free(changed);free(restored);
        exit(detected && equal?2:3);
    }
'''


def thread_header(header):
    header=HELPER+'\n'+FILTER_HEADER(header)
    header=once(header,'robotron_filter_inventory(f, ctx) || fprintf(f, "VA_END\\n")',
                'robotron_filter_inventory(f, ctx) || robotron_thread_inventory(f, ctx) || fprintf(f, "VA_END\\n")')
    modes=''.join(' && strcmp(mode,"thread-'+mode+'-corrupt")' for mode in ('schedule','flag','word','pc','wait','queue'))
    header=once(header,'&& strcmp(mode,"filter-strength-corrupt"))','&& strcmp(mode,"filter-strength-corrupt")'+modes+')')
    return once(header,'    int filter_field=',FAULT+'\n    int filter_field=')


def build(source,vpi,vpi_header,out):
    try:
        base.filter_header=thread_header
        base.build(source,vpi,vpi_header,out)
    finally:base.filter_header=FILTER_HEADER
    path=out/'build.json';r=json.loads(path.read_text());r['sources'][str(Path(__file__).resolve())]=sha(Path(__file__))
    r['scope']='Complete preceding board observer plus initialized live threads and queued event bindings. Restored lifecycle/flag/word/PC/wait/queue faults. Wait-event/code/context/object and other referents remain open.'
    path.write_text(json.dumps(r,indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('source','vpi','vpi-header','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();build(a.source,a.vpi,a.vpi_header,a.out)
