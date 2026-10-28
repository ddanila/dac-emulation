#!/usr/bin/env python3
"""Exercise registered memory destruction/reconstruction in complete board snapshots."""
import argparse,json
from pathlib import Path
import build_parameter_continue_bridge as previous
from build_startup_callback_bridge import once
from ttl7406_probe import sha
PREVIOUS=previous.continue_header
BRANCH=r'''
    if(info->vtime>=5e-6){
        int(*control)(unsigned)=dlsym(ctx->vvp_handle,"robotron_vvp_memory_lifecycle");
        if(!control||control(0)!=1)exit(2);
        char*created=display_snapshot(ctx,api);
        int changed=created&&strcmp(before,created);
        if(!changed)exit(3);
        robotron_metadata_log(stderr,"VB_STAGE created\n%s",created);
        unsigned long long saved_sequence[6];char*saved_body[6];
        for(unsigned i=0;i<6;++i){saved_sequence[i]=robotron_metadata_sequence[i];saved_body[i]=robotron_metadata_previous[i];}
        if(control(1)!=1)exit(3);
        char*destroyed=display_snapshot(ctx,api);
        char*direct=NULL;size_t bytes=0;FILE*f=open_memstream(&direct,&bytes);if(!f)exit(3);
        int rc=robotron_memory_inventory(f,ctx);if(fclose(f))exit(3);
        int refused=!destroyed&&rc<0&&!bytes,unchanged=1;
        for(unsigned i=0;i<6;++i)if(saved_sequence[i]!=robotron_metadata_sequence[i]||saved_body[i]!=robotron_metadata_previous[i])unchanged=0;
        if(!refused||!unchanged||control(2)!=1)exit(3);
        char*restored=display_snapshot(ctx,api);int equal=restored&&!strcmp(before,restored);
        if(!equal)exit(3);
        robotron_metadata_log(stderr,"VB_STAGE restored\n%s",restored);
        robotron_metadata_log(stderr,"VB_MEMORY_LIFECYCLE round=%u time=%.17g changed=%d refused=%d cache_unchanged=%d restored=%d\n",parameter_fault_done+1,info->vtime,!!changed,refused,unchanged,equal);
        free(before);free(created);free(destroyed);free(direct);free(restored);
        ++parameter_fault_done;return;
    }

'''


def lifecycle_header(header):
    header=PREVIOUS(header)
    header=once(header,'    if(parameter_fault_done)return;','''    if(parameter_fault_done==2)return;
    if(parameter_fault_done==1 && (info->vtime<6e-6 || strcmp(phase,"before-step")))return;''')
    header=header.replace('"parameter-word-corrupt"','"parameter-memory-lifecycle"')
    start=header.index('    int parameter_field=');end=header.index('    int all_signal_field=',start)
    return header[:start]+BRANCH+header[end:]


def build(source,vpi,vpi_header,out):
    try:previous.continue_header=lifecycle_header;previous.build(source,vpi,vpi_header,out)
    finally:previous.continue_header=PREVIOUS
    p=out/'build.json';r=json.loads(p.read_text());r['sources'][str(Path(__file__).resolve())]=sha(Path(__file__))
    r['scope']='Selected 5-us and 6-us complete board snapshots allocate a test memory, destroy it with direct/combined refusal and unchanged logger caches, detach the stale entry and require exact restoration. Normal HDL continues through the control window. No full continuous-lifetime or graph teardown qualification.'
    p.write_text(json.dumps(r,indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('source','vpi','vpi-header','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();build(a.source,a.vpi,a.vpi_header,a.out)
