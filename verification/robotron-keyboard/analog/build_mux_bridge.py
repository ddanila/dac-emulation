#!/usr/bin/env python3
"""Add lossless static mux payloads to every preceding board layer."""
import argparse,json
from pathlib import Path
import build_signal_bridge as base
from build_startup_callback_bridge import once
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent
SIGNAL_HEADER=base.signal_header
HELPER=r'''
static int robotron_mux_inventory(FILE *f,struct ng_vvp *ctx)
{
    int (*inventory)(FILE*)=dlsym(ctx->vvp_handle,"robotron_vvp_mux_delta_inventory");
    return inventory ? inventory(f) : -1;
}
static int robotron_mux_fault(struct ng_vvp *ctx,int field)
{
    int (*toggle)(int)=dlsym(ctx->vvp_handle,"robotron_vvp_mux_toggle");
    return toggle ? toggle(field) : -1;
}
static void robotron_mux_reference(struct ng_vvp *ctx)
{
    static struct ng_vvp *owner;
    if(owner && owner!=ctx)exit(3);
    if(owner)return;
    int (*reference)(FILE*)=dlsym(ctx->vvp_handle,"robotron_vvp_mux_reference");
    if(!reference || reference(stderr))exit(2);
    owner=ctx;
}
'''
FAULT=r'''
    int mux_field=!strcmp(mode,"mux-a-corrupt")?0:!strcmp(mode,"mux-b-corrupt")?1:!strcmp(mode,"mux-select-corrupt")?2:!strcmp(mode,"mux-run-corrupt")?3:-1;
    if(mux_field>=0 && (mux_field==0 ? robotron_start_phase==1 : info->vtime>=5e-6)) {
        if(robotron_mux_fault(ctx,mux_field)!=1)exit(2);
        char *changed=display_snapshot(ctx,api);
        if(robotron_mux_fault(ctx,mux_field)!=1)exit(3);
        char *restored=display_snapshot(ctx,api);
        int detected=changed && strcmp(before,changed)!=0;
        int equal=restored && !strcmp(before,restored);
        if(changed)fprintf(stderr,"VB_STAGE changed\n%s",changed);
        if(restored)fprintf(stderr,"VB_STAGE restored\n%s",restored);
        fprintf(stderr,"VB_MUX_FAULT field=%d changed=%d restored=%d\n",mux_field,detected,equal);
        free(before);free(changed);free(restored);
        exit(detected && equal?2:3);
    }
'''


def mux_header(header):
    header=HELPER+'\n'+SIGNAL_HEADER(header)
    header=once(header,'robotron_signal_inventory(f, ctx) || fprintf(f, "VA_END\\n")',
                'robotron_signal_inventory(f, ctx) || robotron_mux_inventory(f, ctx) || fprintf(f, "VA_END\\n")')
    modes=''.join(' && strcmp(mode,"mux-'+name+'-corrupt")' for name in ('a','b','select','run'))
    header=once(header,'&& strcmp(mode,"signal-active-corrupt"))','&& strcmp(mode,"signal-active-corrupt")'+modes+')')
    header=once(header,'    robotron_signal_reference(ctx);','    robotron_signal_reference(ctx);\n    robotron_mux_reference(ctx);')
    return once(header,'    int signal_field=',FAULT+'\n    int signal_field=')


def build(source,vpi,vpi_header,out):
    try:
        base.signal_header=mux_header
        base.build(source,vpi,vpi_header,out)
    finally:base.signal_header=SIGNAL_HEADER
    path=out/'build.json';r=json.loads(path.read_text());r['sources'][str(Path(__file__).resolve())]=sha(Path(__file__))
    r['scope']='Mux pending-destination faults remain in standalone native controls. All preceding board layers plus full-scan static mux deltas and existing native class bindings. Input-cache, selection and run-history faults restore before execution. Other functor payloads and callbacks remain separate.'
    path.write_text(json.dumps(r,indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('source','vpi','vpi-header','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();build(a.source,a.vpi,a.vpi_header,a.out)
