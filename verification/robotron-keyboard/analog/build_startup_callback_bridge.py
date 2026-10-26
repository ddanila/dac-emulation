#!/usr/bin/env python3
"""Pair the startup lifetime observer with all existing board state observers."""
import argparse,json
from pathlib import Path
import build_output_callback_bridge as base
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent
OUTPUT_HEADER=base.output_header
OUTPUT_VPI=base.output_vpi
START_FAULT=r'''
    int start_field = !strcmp(mode,"startup-user-corrupt") ? 0 :
        !strcmp(mode,"startup-function-corrupt") ? 1 :
        !strcmp(mode,"startup-time-corrupt") ? 2 :
        !strcmp(mode,"startup-link-corrupt") ? 3 : -1;
    if (start_field>=0 && robotron_start_phase==1) {
        if (robotron_start_fault(start_field)!=1) exit(2);
        char *changed=display_snapshot(ctx,api);
        if (robotron_start_fault(start_field)!=1) exit(3);
        char *restored=display_snapshot(ctx,api);
        int rejected=changed==NULL;
        int equal=restored && !strcmp(before,restored);
        if (restored) fprintf(stderr,"VB_STAGE restored\n%s",restored);
        fprintf(stderr,"VB_START_FAULT field=%d rejected=%d restored=%d\n",start_field,rejected,equal);
        free(before);free(changed);free(restored);
        exit(rejected && equal ? 2 : 3);
    }
'''

def once(source,old,new):
    if source.count(old)!=1:raise ValueError('Changed startup handoff boundary')
    return source.replace(old,new)

def startup_header(header):
    header=OUTPUT_HEADER(header)
    header=(HERE/'fixtures/startup_callback_bridge.h').read_text()+'\n'+header
    header=once(header,'robotron_output_inventory(f, ctx) || fprintf(f, "VA_END\\n")',
                'robotron_output_inventory(f, ctx) || robotron_start_inventory(f, ctx) || fprintf(f, "VA_END\\n")')
    header=once(header,'&& strcmp(mode,"output-link-corrupt"))',
                '&& strcmp(mode,"output-link-corrupt") && strcmp(mode,"startup-user-corrupt") && strcmp(mode,"startup-function-corrupt") && strcmp(mode,"startup-time-corrupt") && strcmp(mode,"startup-link-corrupt"))')
    return once(header,'    int output_field =',START_FAULT+'\n    int output_field =')

def startup_vpi(source):
    source=OUTPUT_VPI(source)
    old='    Robotron_sync_identity((struct ng_vvp*)cbd.user_data, next_advance_cb);\n    vpi_register_cb(&cbd);'
    source=once(source,old,'''    Robotron_sync_identity((struct ng_vvp*)cbd.user_data, next_advance_cb);
    extern void Robotron_start_registration(struct ng_vvp*,vpiHandle,PLI_INT32(*)(struct t_cb_data*));
    vpiHandle registered = vpi_register_cb(&cbd);
    Robotron_start_registration((struct ng_vvp*)cbd.user_data,registered,start_cb);''')
    source=once(source,'    cr_init(&ctx->cr_ctx);','''    extern void Robotron_start_phase(struct ng_vvp*,int);
    Robotron_start_phase(ctx,1);
    cr_init(&ctx->cr_ctx);''')
    return once(source,'    next_advance_cb(cb);\n    return 0;',
                '    next_advance_cb(cb);\n    Robotron_start_phase(ctx,2);\n    return 0;')

def build(source,vpi,vpi_header,out):
    try:
        base.output_header,base.output_vpi=startup_header,startup_vpi
        base.build(source,vpi,vpi_header,out)
    finally:base.output_header,base.output_vpi=OUTPUT_HEADER,OUTPUT_VPI
    path=out/'build.json';r=json.loads(path.read_text())
    for p in (Path(__file__).resolve(),HERE/'fixtures/startup_callback_bridge.h'):
        r['sources'][str(p)]=sha(p)
    r['scope']='Explicit startup registration and phase handoffs, active callback lifetime at paused boundaries and destruction after return. Combined with existing initialized-port/output/wrapper/stop/display observers. Requires matched board controls; startup/recovery and general rollback remain open.'
    path.write_text(json.dumps(r,indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('source','vpi','vpi-header','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();build(a.source,a.vpi,a.vpi_header,a.out)
