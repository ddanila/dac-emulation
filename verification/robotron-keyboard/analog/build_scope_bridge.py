#!/usr/bin/env python3
"""Add static-scope hierarchy and membership to all preceding board layers."""
import argparse,json
from pathlib import Path
import build_code_binding_bridge as base
from build_startup_callback_bridge import once
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent
CODE_HEADER=base.code_header
HELPER=r'''
static int robotron_scope_inventory(FILE *f,struct ng_vvp *ctx)
{
    int (*inventory)(FILE*)=dlsym(ctx->vvp_handle,"robotron_vvp_scope_inventory");
    return inventory ? inventory(f) : -1;
}
static int robotron_scope_fault(struct ng_vvp *ctx)
{
    int (*toggle)(void)=dlsym(ctx->vvp_handle,"robotron_vvp_scope_toggle");
    return toggle ? toggle() : -1;
}
'''
FAULT=r'''
    int scope_early=!strcmp(mode,"scope-startup-corrupt");
    int scope_late=!strcmp(mode,"scope-late-corrupt");
    if((scope_early && robotron_start_phase==1) || (scope_late && info->vtime>=5e-6)) {
        if(robotron_scope_fault(ctx)!=1)exit(2);
        char *changed=display_snapshot(ctx,api);
        if(robotron_scope_fault(ctx)!=1)exit(3);
        char *restored=display_snapshot(ctx,api);
        int detected=changed && strcmp(before,changed)!=0;
        int equal=restored && !strcmp(before,restored);
        if(changed)fprintf(stderr,"VB_STAGE changed\n%s",changed);
        if(restored)fprintf(stderr,"VB_STAGE restored\n%s",restored);
        fprintf(stderr,"VB_SCOPE_FAULT field=%d changed=%d restored=%d\n",scope_late,detected,equal);
        free(before);free(changed);free(restored);
        exit(detected && equal?2:3);
    }
'''



def scope_header(header):
    header=HELPER+'\n'+CODE_HEADER(header)
    header=once(header,'robotron_code_inventory(f, ctx) || fprintf(f, "VA_END\\n")',
                'robotron_code_inventory(f, ctx) || robotron_scope_inventory(f, ctx) || fprintf(f, "VA_END\\n")')
    header=once(header,'&& strcmp(mode,"code-foreign-corrupt"))',
                '&& strcmp(mode,"code-foreign-corrupt") && strcmp(mode,"scope-startup-corrupt") && strcmp(mode,"scope-late-corrupt"))')
    return once(header,'    int code_field=',FAULT+'\n    int code_field=')


def build(source,vpi,vpi_header,out):
    try:
        base.code_header=scope_header
        base.build(source,vpi,vpi_header,out)
    finally:base.code_header=CODE_HEADER
    path=out/'build.json';r=json.loads(path.read_text());r['sources'][str(Path(__file__).resolve())]=sha(Path(__file__))
    r['scope']='All preceding board layers plus static-scope hierarchy and actual membership; restored membership removal at startup and after 5 us. Scope intern contents and deeper referents remain open.'
    path.write_text(json.dumps(r,indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('source','vpi','vpi-header','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();build(a.source,a.vpi,a.vpi_header,a.out)
