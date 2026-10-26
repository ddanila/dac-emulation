#!/usr/bin/env python3
"""Add pending assignment payloads to the combined paused board observer."""
import argparse,json
from pathlib import Path
import build_startup_callback_bridge as base
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent
START_HEADER=base.startup_header
HELPER=r'''
static int robotron_assignment_inventory(FILE *f,struct ng_vvp *ctx)
{
    int (*inventory)(FILE*)=dlsym(ctx->vvp_handle,"robotron_vvp_assignment_inventory");
    return inventory ? inventory(f) : -1;
}
static int robotron_assignment_fault(struct ng_vvp *ctx,int kind,int field)
{
    int (*toggle)(int,int)=dlsym(ctx->vvp_handle,"robotron_vvp_assignment_toggle");
    return toggle ? toggle(kind,field) : -1;
}
'''
FAULT=r'''
    int assign_kind=0,assign_field=-1;
    const char *assign_modes[]={"assignment-v4-value-corrupt","assignment-v4-target-corrupt","assignment-v4-width-corrupt",
                              "assignment-v8-value-corrupt","assignment-v8-target-corrupt","assignment-v8-strength-corrupt"};
    for(int i=0;i<6;i++) if(!strcmp(mode,assign_modes[i])) {assign_kind=i<3?4:8;assign_field=i%3;}
    if(assign_kind && robotron_start_phase==1) {
        if(robotron_assignment_fault(ctx,assign_kind,assign_field)!=1) exit(2);
        char *changed=display_snapshot(ctx,api);
        if(robotron_assignment_fault(ctx,assign_kind,assign_field)!=1) exit(3);
        char *restored=display_snapshot(ctx,api);
        int detected=changed && strcmp(before,changed)!=0;
        int equal=restored && !strcmp(before,restored);
        if(changed)fprintf(stderr,"VB_STAGE changed\n%s",changed);
        if(restored)fprintf(stderr,"VB_STAGE restored\n%s",restored);
        fprintf(stderr,"VB_ASSIGN_FAULT kind=%d field=%d changed=%d restored=%d\n",assign_kind,assign_field,detected,equal);
        free(before);free(changed);free(restored);
        exit(detected && equal?2:3);
    }
'''

def assignment_header(header):
    header=HELPER+'\n'+START_HEADER(header)
    header=base.once(header,'robotron_start_inventory(f, ctx) || fprintf(f, "VA_END\\n")',
                     'robotron_start_inventory(f, ctx) || robotron_assignment_inventory(f, ctx) || fprintf(f, "VA_END\\n")')
    modes=''.join(' && strcmp(mode,"assignment-'+mode+'-corrupt")' for mode in ('v4-value','v4-target','v4-width','v8-value','v8-target','v8-strength'))
    header=base.once(header,'&& strcmp(mode,"startup-link-corrupt"))','&& strcmp(mode,"startup-link-corrupt")'+modes+')')
    return base.once(header,'    int start_field =',FAULT+'\n    int start_field =')

def build(source,vpi,vpi_header,out):
    try:
        base.startup_header=assignment_header
        base.build(source,vpi,vpi_header,out)
    finally:base.startup_header=START_HEADER
    path=out/'build.json';r=json.loads(path.read_text());r['sources'][str(Path(__file__).resolve())]=sha(Path(__file__))
    r['scope']='Combined board observer with typed queued assignments. Payload/destination-port/slice-width/strength faults restored before scheduler continuation. Target referents, other event families and general rollback remain open.'
    path.write_text(json.dumps(r,indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('source','vpi','vpi-header','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();build(a.source,a.vpi,a.vpi_header,a.out)
