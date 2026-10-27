#!/usr/bin/env python3
"""Add complete typed operand deltas to all preceding board layers."""
import argparse,json
from pathlib import Path
import build_scope_bridge as base
from build_startup_callback_bridge import once
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent
SCOPE_HEADER=base.scope_header
HELPER=r'''
static int robotron_operand_inventory(FILE *f,struct ng_vvp *ctx)
{
    int (*inventory)(FILE*,int)=dlsym(ctx->vvp_handle,"robotron_vvp_code_operand_inventory");
    return inventory ? inventory(f,1) : -1;
}
static int robotron_operand_fault(struct ng_vvp *ctx,int field)
{
    int (*toggle)(int)=dlsym(ctx->vvp_handle,"robotron_vvp_code_operand_toggle");
    return toggle ? toggle(field) : -1;
}
static void robotron_operand_reference(struct ng_vvp *ctx)
{
    static struct ng_vvp *owner;
    if(owner && owner!=ctx)exit(3);
    if(owner)return;
    int (*reference)(FILE*)=dlsym(ctx->vvp_handle,"robotron_vvp_code_operand_reference");
    if(!reference || reference(stderr))exit(2);
    owner=ctx;
}
'''
FAULT=r'''
    int operand_field=!strcmp(mode,"operand-immediate-corrupt")?0:!strcmp(mode,"operand-target-corrupt")?1:!strcmp(mode,"operand-handle-corrupt")?2:!strcmp(mode,"operand-unknown-corrupt")?3:-1;
    if(operand_field>=0 && ((operand_field==1 || operand_field==2) ? info->vtime>=5e-6 : robotron_start_phase==1)) {
        if(robotron_operand_fault(ctx,operand_field)!=1)exit(2);
        char *changed=display_snapshot(ctx,api);
        if(robotron_operand_fault(ctx,operand_field)!=1)exit(3);
        char *restored=display_snapshot(ctx,api);
        int detected=operand_field==3 ? changed==NULL : changed && strcmp(before,changed)!=0;
        int equal=restored && !strcmp(before,restored);
        if(changed)fprintf(stderr,"VB_STAGE changed\n%s",changed);
        if(restored)fprintf(stderr,"VB_STAGE restored\n%s",restored);
        if(operand_field==3)fprintf(stderr,"VB_OPERAND_REFUSAL field=3 rejected=%d restored=%d\n",detected,equal);
        else fprintf(stderr,"VB_OPERAND_FAULT field=%d changed=%d restored=%d\n",operand_field,detected,equal);
        free(before);free(changed);free(restored);
        exit(detected && equal?2:3);
    }
'''


def operand_header(header):
    header=HELPER+'\n'+SCOPE_HEADER(header)
    header=once(header,'robotron_scope_inventory(f, ctx) || fprintf(f, "VA_END\\n")',
                'robotron_scope_inventory(f, ctx) || robotron_operand_inventory(f, ctx) || fprintf(f, "VA_END\\n")')
    modes=''.join(' && strcmp(mode,"operand-'+name+'-corrupt")' for name in ('immediate','target','handle','unknown'))
    header=once(header,'&& strcmp(mode,"scope-late-corrupt"))','&& strcmp(mode,"scope-late-corrupt")'+modes+')')
    header=once(header,'    char *before = display_snapshot(ctx, api);','    robotron_operand_reference(ctx);\n    char *before = display_snapshot(ctx, api);')
    return once(header,'    int scope_early=',FAULT+'\n    int scope_early=')


def build(source,vpi,vpi_header,out):
    try:
        base.scope_header=operand_header
        base.build(source,vpi,vpi_header,out)
    finally:base.scope_header=SCOPE_HEADER
    path=out/'build.json';r=json.loads(path.read_text());r['sources'][str(Path(__file__).resolve())]=sha(Path(__file__))
    r['scope']='All preceding board layers plus complete typed operand reference/deltas. Actual immediate, code-target and handle faults restore before scheduling; unknown native opcode is refused. Referenced object contents remain open.'
    path.write_text(json.dumps(r,indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('source','vpi','vpi-header','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();build(a.source,a.vpi,a.vpi_header,a.out)
