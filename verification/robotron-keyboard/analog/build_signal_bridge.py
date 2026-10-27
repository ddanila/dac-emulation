#!/usr/bin/env python3
"""Add lossless static signal payloads to every preceding board layer."""
import argparse,json
from pathlib import Path
import build_wire_bridge as base
from build_startup_callback_bridge import once
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent
WIRE_HEADER=base.wire_header
HELPER=r'''
static int robotron_signal_inventory(FILE *f,struct ng_vvp *ctx)
{
    int (*inventory)(FILE*)=dlsym(ctx->vvp_handle,"robotron_vvp_signal_delta_inventory");
    return inventory ? inventory(f) : -1;
}
static int robotron_signal_fault(struct ng_vvp *ctx,int field)
{
    int (*toggle)(int)=dlsym(ctx->vvp_handle,"robotron_vvp_signal_toggle");
    return toggle ? toggle(field) : -1;
}
static void robotron_signal_reference(struct ng_vvp *ctx)
{
    static struct ng_vvp *owner;
    if(owner && owner!=ctx)exit(3);
    if(owner)return;
    int (*reference)(FILE*)=dlsym(ctx->vvp_handle,"robotron_vvp_signal_reference");
    int (*types)(FILE*)=dlsym(ctx->vvp_handle,"robotron_vvp_net_types");
    if(!reference || !types || types(stderr) || reference(stderr))exit(2);
    owner=ctx;
}
'''
FAULT=r'''
    int signal_field=!strcmp(mode,"signal-init-corrupt")?0:!strcmp(mode,"signal-value-corrupt")?1:!strcmp(mode,"signal-active-corrupt")?4:-1;
    if(signal_field>=0 && (signal_field==0 ? robotron_start_phase==1 : info->vtime>=5e-6)) {
        if(robotron_signal_fault(ctx,signal_field)!=1)exit(2);
        char *changed=display_snapshot(ctx,api);
        if(robotron_signal_fault(ctx,signal_field)!=1)exit(3);
        char *restored=display_snapshot(ctx,api);
        int detected=changed && strcmp(before,changed)!=0;
        int equal=restored && !strcmp(before,restored);
        if(changed)fprintf(stderr,"VB_STAGE changed\n%s",changed);
        if(restored)fprintf(stderr,"VB_STAGE restored\n%s",restored);
        fprintf(stderr,"VB_SIGNAL_FAULT field=%d changed=%d restored=%d\n",signal_field,detected,equal);
        free(before);free(changed);free(restored);
        exit(detected && equal?2:3);
    }
'''


def signal_header(header):
    header=HELPER+'\n'+WIRE_HEADER(header)
    header=once(header,'robotron_wire_inventory(f, ctx) || fprintf(f, "VA_END\\n")',
                'robotron_wire_inventory(f, ctx) || robotron_signal_inventory(f, ctx) || fprintf(f, "VA_END\\n")')
    modes=''.join(' && strcmp(mode,"signal-'+name+'-corrupt")' for name in ('init','value','active'))
    header=once(header,'&& strcmp(mode,"wire8-propagate-corrupt"))','&& strcmp(mode,"wire8-propagate-corrupt")'+modes+')')
    header=once(header,'    robotron_wire_reference(ctx);','    robotron_wire_reference(ctx);\n    robotron_signal_reference(ctx);')
    return once(header,'    int wire_kind=',FAULT+'\n    int wire_kind=')


def build(source,vpi,vpi_header,out):
    try:
        base.wire_header=signal_header
        base.build(source,vpi,vpi_header,out)
    finally:base.wire_header=WIRE_HEADER
    path=out/'build.json';r=json.loads(path.read_text());r['sources'][str(Path(__file__).resolve())]=sha(Path(__file__))
    r['scope']='All preceding board layers plus full-scan static signal deltas and initial native class bindings. Initialization, stored-value and assignment-active flag faults restore before execution. Other functor payloads and callbacks remain separate.'
    path.write_text(json.dumps(r,indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('source','vpi','vpi-header','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();build(a.source,a.vpi,a.vpi_header,a.out)
