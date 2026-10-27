#!/usr/bin/env python3
"""Add restored native typed-metadata faults to the combined signal bridge."""
import argparse,json
from pathlib import Path
import build_callback_signal_bridge as base
from build_startup_callback_bridge import once
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent
PREVIOUS_HEADER=base.signal_header
NAMES=('signed','range','node','name','cache','scope')
HELPER=r'''
static int robotron_typed_fault(struct ng_vvp*ctx,int field)
{
    if(ctx!=robotron_typed_signal_context || ctx->ins>=robotron_typed_signal_count)return -1;
    int(*toggle)(unsigned long long,int)=dlsym(ctx->vvp_handle,"robotron_vvp_signal_handle_toggle");
    return toggle?toggle(robotron_typed_signal_bindings[ctx->ins].id,field):-1;
}
static char*robotron_typed_text(struct ng_vvp*ctx)
{
    char*text=NULL;size_t size=0;FILE*f=open_memstream(&text,&size);if(!f)return NULL;
    int result=robotron_typed_signal_inventory(f,ctx);if(fclose(f))result=-1;
    if(result){free(text);return NULL;}return text;
}
'''
FAULT=r'''
    int typed_field=FIELD_SELECTION;
    if(typed_field>=0 && robotron_start_phase==1){
        char*direct_before=robotron_typed_text(ctx);if(!direct_before)exit(2);
        if(robotron_typed_fault(ctx,typed_field)!=1)exit(2);
        char*direct=robotron_typed_text(ctx);
        char*changed=display_snapshot(ctx,api);
        if(robotron_typed_fault(ctx,typed_field)!=1)exit(3);
        char*restored=display_snapshot(ctx,api);
        int direct_ok=typed_field<2?(direct&&strcmp(direct_before,direct)!=0):direct==NULL;
        int changed_ok=changed&&strcmp(before,changed)!=0,rejected=changed==NULL;
        int equal=restored&&!strcmp(before,restored);
        if(changed)fprintf(stderr,"VB_STAGE changed\n%s",changed);
        if(restored)fprintf(stderr,"VB_STAGE restored\n%s",restored);
        fprintf(stderr,"VB_TYPED_SIGNAL_FAULT field=%d direct=%d changed=%d rejected=%d restored=%d\n",typed_field,direct_ok,changed_ok,rejected,equal);
        free(direct_before);free(direct);free(before);free(changed);free(restored);
        exit(direct_ok&&equal&&(typed_field<2?changed_ok:rejected)?2:3);
    }
'''


def fault_header(header):
    header='static int robotron_typed_fault(struct ng_vvp*,int);\nstatic char*robotron_typed_text(struct ng_vvp*);\n'+PREVIOUS_HEADER(header)+'\n'+HELPER
    modes=''.join(' && strcmp(mode,"typed-signal-'+name+'-corrupt")' for name in NAMES)
    header=once(header,'&& strcmp(mode,"callback-list-link-corrupt"))','&& strcmp(mode,"callback-list-link-corrupt")'+modes+')')
    selection=''.join('!strcmp(mode,"typed-signal-'+name+'-corrupt")?'+str(i)+':' for i,name in enumerate(NAMES))+'-1'
    return once(header,'    int callback_list_field=',FAULT.replace('FIELD_SELECTION',selection)+'\n    int callback_list_field=')


def build(source,vpi,vpi_header,out):
    try:
        base.signal_header=fault_header;base.build(source,vpi,vpi_header,out)
    finally:base.signal_header=PREVIOUS_HEADER
    p=out/'build.json';r=json.loads(p.read_text());r['sources'][str(Path(__file__).resolve())]=sha(Path(__file__))
    r['scope']='Combined typed signal observation with native signedness/range changes and node/name/cache/scope refusal controls. Direct typed and complete snapshots must detect each fault; exact full state restoration occurs before termination. Existing callback fault controls remain. Operational normal/transient qualification remains separate.'
    p.write_text(json.dumps(r,indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('source','vpi','vpi-header','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();build(a.source,a.vpi,a.vpi_header,a.out)
