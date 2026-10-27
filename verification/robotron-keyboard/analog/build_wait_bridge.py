#!/usr/bin/env python3
"""Add wait-event heads and histories to the board observer."""
import argparse,json
from pathlib import Path
import build_thread_bridge as base
from build_startup_callback_bridge import once
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent
THREAD_HEADER=base.thread_header
HELPER=r'''
static int robotron_wait_inventory(FILE *f,struct ng_vvp *ctx)
{
    int (*inventory)(FILE*)=dlsym(ctx->vvp_handle,"robotron_vvp_wait_inventory");
    return inventory ? inventory(f) : -1;
}
static int robotron_wait_fault(struct ng_vvp *ctx,int field)
{
    int (*toggle)(int)=dlsym(ctx->vvp_handle,"robotron_vvp_wait_toggle");
    return toggle ? toggle(field) : -1;
}
'''
FAULT=r'''
    int wait_field=-1;
    const char *wait_modes[]={"wait-head-corrupt","wait-mask-corrupt","wait-history-corrupt","wait-cache-corrupt"};
    for(int i=0;i<4;i++)if(!strcmp(mode,wait_modes[i]))wait_field=i;
    if(wait_field>=0 && ((wait_field==0 || wait_field==3) ? info->vtime>=5e-6 : robotron_start_phase==1)) {
        if(robotron_wait_fault(ctx,wait_field)!=1)exit(2);
        char *changed=display_snapshot(ctx,api);
        if(robotron_wait_fault(ctx,wait_field)!=1)exit(3);
        char *restored=display_snapshot(ctx,api);
        int detected=changed && strcmp(before,changed)!=0;
        int equal=restored && !strcmp(before,restored);
        if(changed)fprintf(stderr,"VB_STAGE changed\n%s",changed);
        if(restored)fprintf(stderr,"VB_STAGE restored\n%s",restored);
        fprintf(stderr,"VB_WAIT_FAULT field=%d changed=%d restored=%d\n",wait_field,detected,equal);
        free(before);free(changed);free(restored);
        exit(detected && equal?2:3);
    }
'''


def wait_header(header):
    header=HELPER+'\n'+THREAD_HEADER(header)
    header=once(header,'robotron_thread_inventory(f, ctx) || fprintf(f, "VA_END\\n")',
                'robotron_thread_inventory(f, ctx) || robotron_wait_inventory(f, ctx) || fprintf(f, "VA_END\\n")')
    modes=''.join(' && strcmp(mode,"wait-'+mode+'-corrupt")' for mode in ('head','mask','history','cache'))
    header=once(header,'&& strcmp(mode,"thread-queue-corrupt"))','&& strcmp(mode,"thread-queue-corrupt")'+modes+')')
    return once(header,'    int thread_field=',FAULT+'\n    int thread_field=')


def build(source,vpi,vpi_header,out):
    try:
        base.thread_header=wait_header
        base.build(source,vpi,vpi_header,out)
    finally:base.thread_header=THREAD_HEADER
    path=out/'build.json';r=json.loads(path.read_text());r['sources'][str(Path(__file__).resolve())]=sha(Path(__file__))
    r['scope']='All preceding board layers plus wait-event heads and initialized caches. Restored head/mask/history/cache faults require matched board review; deeper referents and broader windows remain open.'
    path.write_text(json.dumps(r,indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('source','vpi','vpi-header','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();build(a.source,a.vpi,a.vpi_header,a.out)
