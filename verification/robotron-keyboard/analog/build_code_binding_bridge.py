#!/usr/bin/env python3
"""Add allocated-code PC binding to the board observer."""
import argparse,json
from pathlib import Path
import build_wait_bridge as base
from build_startup_callback_bridge import once
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent
WAIT_HEADER=base.wait_header
HELPER=r'''
static int robotron_code_inventory(FILE *f,struct ng_vvp *ctx)
{
    int (*inventory)(FILE*)=dlsym(ctx->vvp_handle,"robotron_vvp_thread_code_inventory");
    return inventory ? inventory(f) : -1;
}
static int robotron_code_fault(struct ng_vvp *ctx,int field)
{
    int (*toggle)(int)=dlsym(ctx->vvp_handle,"robotron_vvp_thread_toggle");
    return toggle ? toggle(field) : -1;
}
'''
FAULT=r'''
    int code_field=!strcmp(mode,"code-null-corrupt")?3:!strcmp(mode,"code-foreign-corrupt")?11:-1;
    if(code_field>=0 && robotron_start_phase==1) {
        if(robotron_code_fault(ctx,code_field)!=1)exit(2);
        char *changed=display_snapshot(ctx,api);
        if(robotron_code_fault(ctx,code_field)!=1)exit(3);
        char *restored=display_snapshot(ctx,api);
        int detected=changed && strcmp(before,changed)!=0;
        int equal=restored && !strcmp(before,restored);
        if(changed)fprintf(stderr,"VB_STAGE changed\n%s",changed);
        if(restored)fprintf(stderr,"VB_STAGE restored\n%s",restored);
        fprintf(stderr,"VB_CODE_FAULT field=%d changed=%d restored=%d\n",code_field,detected,equal);
        free(before);free(changed);free(restored);
        exit(detected && equal?2:3);
    }
'''


def code_header(header):
    header=HELPER+'\n'+WAIT_HEADER(header)
    header=once(header,'robotron_wait_inventory(f, ctx) || fprintf(f, "VA_END\\n")',
                'robotron_wait_inventory(f, ctx) || robotron_code_inventory(f, ctx) || fprintf(f, "VA_END\\n")')
    modes=''.join(' && strcmp(mode,"code-'+mode+'-corrupt")' for mode in ('null','foreign'))
    header=once(header,'&& strcmp(mode,"wait-cache-corrupt"))','&& strcmp(mode,"wait-cache-corrupt")'+modes+')')
    return once(header,'    int wait_field=',FAULT+'\n    int wait_field=')



def build(source,vpi,vpi_header,out):
    try:
        base.wait_header=code_header
        base.build(source,vpi,vpi_header,out)
    finally:base.wait_header=WAIT_HEADER
    path=out/'build.json';r=json.loads(path.read_text());r['sources'][str(Path(__file__).resolve())]=sha(Path(__file__))
    r['scope']='All preceding board layers plus native PC/code allocation binding; restored null and foreign PC faults before execution. Full operands and referenced objects remain open.'
    path.write_text(json.dumps(r,indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('source','vpi','vpi-header','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();build(a.source,a.vpi,a.vpi_header,a.out)
