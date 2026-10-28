#!/usr/bin/env python3
"""Exercise unsupported parameter refusal and restored complete board observation."""
import argparse,json
from pathlib import Path
import build_parameter_lifecycle_bridge as previous
from ttl7406_probe import sha
PREVIOUS=previous.BRANCH
BRANCH=r'''
    if(info->vtime>=5e-6){
        unsigned kind=!strcmp(mode,"parameter-lifecycle-binary")?0:!strcmp(mode,"parameter-lifecycle-real")?1:!strcmp(mode,"parameter-lifecycle-string")?2:3;
        int(*control)(unsigned,unsigned)=dlsym(ctx->vvp_handle,"robotron_vvp_parameter_refusal_cycle");
        if(kind>2||!control||control(0,kind)!=1)exit(2);
        unsigned long long saved_sequence[6];char*saved_body[6];
        for(unsigned i=0;i<6;++i){saved_sequence[i]=robotron_metadata_sequence[i];saved_body[i]=robotron_metadata_previous[i];}
        for(unsigned phase=0;phase<2;++phase){
            if(phase && control(1,kind)!=1)exit(3);
            char*combined=display_snapshot(ctx,api);
            char*direct=NULL;size_t bytes=0;FILE*f=open_memstream(&direct,&bytes);if(!f)exit(3);
            int rc=robotron_parameter_inventory(f,ctx);if(fclose(f))exit(3);
            if(combined||rc>=0||bytes)exit(3);
            for(unsigned i=0;i<6;++i)if(saved_sequence[i]!=robotron_metadata_sequence[i]||saved_body[i]!=robotron_metadata_previous[i])exit(3);
            free(combined);free(direct);
        }
        if(control(2,kind)!=1)exit(3);
        char*restored=display_snapshot(ctx,api);int equal=restored&&!strcmp(before,restored);
        if(!equal)exit(3);
        robotron_metadata_log(stderr,"VB_STAGE restored\n%s",restored);
        robotron_metadata_log(stderr,"VB_PARAMETER_RECOVERY round=%u time=%.17g live_refused=1 destroyed_refused=1 cache_unchanged=1 restored=%d\n",parameter_fault_done+1,info->vtime,equal);
        free(before);free(restored);++parameter_fault_done;return;
    }

'''


def build(source,vpi,vpi_header,out):
    try:previous.BRANCH=BRANCH;previous.build(source,vpi,vpi_header,out)
    finally:previous.BRANCH=PREVIOUS
    p=out/'build.json';r=json.loads(p.read_text());r['sources'][str(Path(__file__).resolve())]=sha(Path(__file__))
    r['scope']='Two selected complete board boundaries allocate an unsupported test parameter, require direct/combined refusal while live and after native destruction, then detach the stale scope entry and restore complete observation byte-for-byte. No unsupported payload admission or general graph teardown qualification.'
    p.write_text(json.dumps(r,indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('source','vpi','vpi-header','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();build(a.source,a.vpi,a.vpi_header,a.out)
