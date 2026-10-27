#!/usr/bin/env python3
"""Exercise late parameter-class refusal through complete snapshot construction."""
import argparse,json
from pathlib import Path
import build_parameter_continue_bridge as previous
from build_startup_callback_bridge import once
from ttl7406_probe import sha
PREVIOUS=previous.continue_header
CHECK=r'''
        unsigned long long saved_sequence[6];char*saved_body[6];
        for(unsigned i=0;i<6;++i){saved_sequence[i]=robotron_metadata_sequence[i];saved_body[i]=robotron_metadata_previous[i];}
        char*direct=robotron_parameter_text(ctx);char*combined=display_snapshot(ctx,api);
        int refused=!direct&&!combined,unchanged=1;
        for(unsigned i=0;i<6;++i)if(saved_sequence[i]!=robotron_metadata_sequence[i]||saved_body[i]!=robotron_metadata_previous[i])unchanged=0;
        free(direct);free(combined);
        robotron_metadata_log(stderr,"VB_PARAMETER_LATE round=%u time=%.17g refused=%d cache_unchanged=%d\n",parameter_fault_done+1,info->vtime,refused,unchanged);
        if(!refused||!unchanged)exit(3);
'''


def refusal_header(header):
    header=PREVIOUS(header)
    header=once(header,'    if(parameter_fault_done)return;','''    if(parameter_fault_done==2)return;
    if(parameter_fault_done==1 && (info->vtime<6e-6 || strcmp(phase,"before-step")))return;''')
    marker='    char *before = display_snapshot(ctx, api);'
    header=once(header,marker,'''    if(parameter_fault_done==1){
'''+CHECK+'''        parameter_fault_done=2;return;
    }
'''+marker)
    start=header.index('    int parameter_field=');end=header.index('    int all_signal_field=',start)
    branch=r'''    if(info->vtime>=5e-6){
        unsigned kind=!strcmp(mode,"parameter-late-binary")?0:!strcmp(mode,"parameter-late-real")?1:!strcmp(mode,"parameter-late-string")?2:3;
        int(*add)(unsigned)=dlsym(ctx->vvp_handle,"robotron_vvp_parameter_add_unsupported");
        if(kind>2||!add||add(kind)!=1)exit(2);
'''+CHECK+r'''        free(before);parameter_fault_done=1;return;
    }

'''
    header=header[:start]+branch+header[end:]
    for old,new in [('word','binary'),('signed','real'),('sized','string')]:
        header=header.replace('"parameter-'+old+'-corrupt"','"parameter-late-'+new+'"')
    return header


def build(source,vpi,vpi_header,out):
    try:previous.continue_header=refusal_header;previous.build(source,vpi,vpi_header,out)
    finally:previous.continue_header=PREVIOUS
    p=out/'build.json';r=json.loads(p.read_text());r['sources'][str(Path(__file__).resolve())]=sha(Path(__file__))
    r['scope']='Startup and pre-allocation full snapshots, then unsupported native parameter allocation at 5 us. Direct and complete snapshots must refuse immediately and after 6 us without compact cache/sequence changes; ordinary execution continues. No removal/restoration of the unsupported object and no post-refusal private state coverage.'
    p.write_text(json.dumps(r,indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('source','vpi','vpi-header','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();build(a.source,a.vpi,a.vpi_header,a.out)
