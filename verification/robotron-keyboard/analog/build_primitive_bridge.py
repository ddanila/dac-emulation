#!/usr/bin/env python3
"""Add cached inverter and static part-select payloads to the combined board observer."""
import argparse,json
from pathlib import Path
import build_assignment_bridge as base
from build_startup_callback_bridge import once
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent
ASSIGNMENT_HEADER=base.assignment_header
HELPER=r'''
static int robotron_primitive_inventory(FILE *f,struct ng_vvp *ctx)
{
    int (*inventory)(FILE*)=dlsym(ctx->vvp_handle,"robotron_vvp_primitive_inventory");
    return inventory ? inventory(f) : -1;
}
static int robotron_primitive_fault(struct ng_vvp *ctx,int kind,int field)
{
    int (*toggle)(int,int)=dlsym(ctx->vvp_handle,"robotron_vvp_primitive_toggle");
    return toggle ? toggle(kind,field) : -1;
}
'''
FAULT=r'''
    int primitive_kind=0,primitive_field=-1;
    const char *primitive_modes[]={"primitive-not-value-corrupt","primitive-not-target-corrupt",
                                 "primitive-part-value-corrupt","primitive-part-target-corrupt","primitive-part-base-corrupt"};
    for(int i=0;i<5;i++) if(!strcmp(mode,primitive_modes[i])) {primitive_kind=i<2?1:2;primitive_field=i<2?i:i-2;}
    if(primitive_kind && robotron_start_phase==1) {
        if(robotron_primitive_fault(ctx,primitive_kind,primitive_field)!=1) exit(2);
        char *changed=display_snapshot(ctx,api);
        if(robotron_primitive_fault(ctx,primitive_kind,primitive_field)!=1) exit(3);
        char *restored=display_snapshot(ctx,api);
        int detected=changed && strcmp(before,changed)!=0;
        int equal=restored && !strcmp(before,restored);
        if(changed)fprintf(stderr,"VB_STAGE changed\n%s",changed);
        if(restored)fprintf(stderr,"VB_STAGE restored\n%s",restored);
        fprintf(stderr,"VB_PRIMITIVE_FAULT kind=%d field=%d changed=%d restored=%d\n",primitive_kind,primitive_field,detected,equal);
        free(before);free(changed);free(restored);
        exit(detected && equal?2:3);
    }
'''


def primitive_header(header):
    header=HELPER+'\n'+ASSIGNMENT_HEADER(header)
    header=once(header,'robotron_assignment_inventory(f, ctx) || fprintf(f, "VA_END\\n")',
                'robotron_assignment_inventory(f, ctx) || robotron_primitive_inventory(f, ctx) || fprintf(f, "VA_END\\n")')
    modes=''.join(' && strcmp(mode,"primitive-'+mode+'-corrupt")' for mode in ('not-value','not-target','part-value','part-target','part-base'))
    header=once(header,'&& strcmp(mode,"assignment-v8-strength-corrupt"))','&& strcmp(mode,"assignment-v8-strength-corrupt")'+modes+')')
    return once(header,'    int assign_kind=',FAULT+'\n    int assign_kind=')


def build(source,vpi,vpi_header,out):
    try:
        base.assignment_header=primitive_header
        base.build(source,vpi,vpi_header,out)
    finally:base.assignment_header=ASSIGNMENT_HEADER
    path=out/'build.json';r=json.loads(path.read_text());r['sources'][str(Path(__file__).resolve())]=sha(Path(__file__))
    r['scope']='Combined board observer with cached inverter/static part-select vectors, destination pointers and slice bounds. Restored early faults precede scheduler continuation. Island/thread state, destination referents and general rollback remain open.'
    path.write_text(json.dumps(r,indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('source','vpi','vpi-header','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();build(a.source,a.vpi,a.vpi_header,a.out)
