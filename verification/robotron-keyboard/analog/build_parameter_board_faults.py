#!/usr/bin/env python3
"""Exercise parameter faults on the initialized keyboard before HDL advance."""
import argparse,json,subprocess
from pathlib import Path
import build_parameter_board_budget as base
from build_startup_callback_bridge import once
from ttl7406_probe import sha
EXTRA=r'''
    int(*parameter_toggle)(unsigned)=dlsym(ctx->vvp_handle,"robotron_vvp_parameter_toggle");
    if(!parameter_toggle)exit(2);
    FILE *events=fopen("parameter-faults.txt","w");if(!events)exit(2);
    for(unsigned round=1;round<=2;round++)for(unsigned field=0;field<16;field++) {
        int applicable=field<=6 || (field>=9 && field<=11);
        int status=parameter_toggle(field);
        if(!applicable){
            if(status!=-1)exit(2);
            fprintf(events,"ABSENT %u %u\n",round,field);
        } else {
            if(status!=1)exit(2);
            char *bytes=NULL;size_t size=0;
            FILE *stream=open_memstream(&bytes,&size);if(!stream)exit(2);
            int result=parameters(stream);if(fclose(stream))exit(2);
            if(field<=6){
                if(result || !size)exit(2);
                char name[80];snprintf(name,sizeof(name),"parameter-changed-%u-%u.txt",round,field);
                FILE *output=fopen(name,"w");if(!output || fwrite(bytes,1,size,output)!=size || fclose(output))exit(2);
                fprintf(events,"CHANGED %u %u\n",round,field);
            } else {
                if(result>=0 || size)exit(2);
                fprintf(events,"REFUSED %u %u\n",round,field);
            }
            free(bytes);
            if(parameter_toggle(field)!=1)exit(2);
        }
        char name[80];snprintf(name,sizeof(name),"parameter-restored-%u-%u.txt",round,field);
        callback_budget_file(ctx,parameters,name);
    }
    if(fclose(events))exit(2);
'''


def build(source,vpi,vpi_header,out):
    base.build(source,vpi,vpi_header,out)
    shim=out/'icarus_shim.c';shim.write_text(once(shim.read_text(),base.EXTRA,base.EXTRA+EXTRA))
    p=out/'build.json';r=json.loads(p.read_text());subprocess.run(r['commands'][0],check=True)
    r['sources'][str(Path(__file__).resolve())]=sha(Path(__file__))
    r['outputs']={n:sha(out/n) for n in r['outputs']}
    r['scope']='Two rounds of initialized actual board parameter fields, pointer refusals and absent-family refusals. Exits before HDL advance; no operational transient qualification.'
    p.write_text(json.dumps(r,indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('source','vpi','vpi-header','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();build(a.source,a.vpi,a.vpi_header,a.out)
