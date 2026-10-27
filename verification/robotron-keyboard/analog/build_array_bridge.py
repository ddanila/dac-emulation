#!/usr/bin/env python3
"""Add compact complete array images to all preceding board layers."""
import argparse,json
from pathlib import Path
import build_code_operand_bridge as base
from build_startup_callback_bridge import once
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent
OPERAND_HEADER=base.operand_header
HELPER=r'''
static int robotron_array_inventory(FILE *f,struct ng_vvp *ctx)
{
    int (*inventory)(FILE*)=dlsym(ctx->vvp_handle,"robotron_vvp_array_compact_inventory");
    return inventory ? inventory(f) : -1;
}
static int robotron_array_fault(struct ng_vvp *ctx,int field)
{
    int (*toggle)(int)=dlsym(ctx->vvp_handle,"robotron_vvp_array_toggle");
    return toggle ? toggle(field) : -1;
}
'''
FAULT=r'''
    int array_field=!strcmp(mode,"array-word-corrupt")?0:!strcmp(mode,"array-address-corrupt")?1:!strcmp(mode,"array-link-corrupt")?2:!strcmp(mode,"array-cache-corrupt")?3:-1;
    if(array_field>=0 && (array_field==2 ? robotron_start_phase==1 : info->vtime>=5e-6)) {
        if(robotron_array_fault(ctx,array_field)!=1)exit(2);
        char *changed=display_snapshot(ctx,api);
        if(robotron_array_fault(ctx,array_field)!=1)exit(3);
        char *restored=display_snapshot(ctx,api);
        int detected=changed && strcmp(before,changed)!=0;
        int equal=restored && !strcmp(before,restored);
        if(changed)fprintf(stderr,"VB_STAGE changed\n%s",changed);
        if(restored)fprintf(stderr,"VB_STAGE restored\n%s",restored);
        fprintf(stderr,"VB_ARRAY_FAULT field=%d changed=%d restored=%d\n",array_field,detected,equal);
        free(before);free(changed);free(restored);
        exit(detected && equal?2:3);
    }
'''


def array_header(header):
    header=HELPER+'\n'+OPERAND_HEADER(header)
    header=once(header,'robotron_operand_inventory(f, ctx) || fprintf(f, "VA_END\\n")',
                'robotron_operand_inventory(f, ctx) || robotron_array_inventory(f, ctx) || fprintf(f, "VA_END\\n")')
    modes=''.join(' && strcmp(mode,"array-'+name+'-corrupt")' for name in ('word','address','link','cache'))
    header=once(header,'&& strcmp(mode,"operand-unknown-corrupt"))','&& strcmp(mode,"operand-unknown-corrupt")'+modes+')')
    return once(header,'    int operand_field=',FAULT+'\n    int operand_field=')


def build(source,vpi,vpi_header,out):
    try:
        base.operand_header=array_header
        base.build(source,vpi,vpi_header,out)
    finally:base.operand_header=OPERAND_HEADER
    path=out/'build.json';r=json.loads(path.read_text());r['sources'][str(Path(__file__).resolve())]=sha(Path(__file__))
    r['scope']='All preceding board layers plus complete compact array images. Actual word/address/link/cache faults restore before execution. Net/fanout and callback contents remain separate.'
    path.write_text(json.dumps(r,indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('source','vpi','vpi-header','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();build(a.source,a.vpi,a.vpi_header,a.out)
