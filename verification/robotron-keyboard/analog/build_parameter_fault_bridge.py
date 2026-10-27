#!/usr/bin/env python3
"""Inject isolated parameter faults into complete native board snapshots."""
import argparse,json
from pathlib import Path
import build_parameter_bridge as base
from build_startup_callback_bridge import once
from ttl7406_probe import sha
PREVIOUS_HEADER=base.parameter_header
FIELDS={'word':0,'signed':1,'sized':2,'local':3,'file':4,'line':5,'name':6,'width':9,'scope':10,'name-pointer':11}
HELPER=r'''
static char*robotron_parameter_text(struct ng_vvp*ctx)
{
    char*text=NULL;size_t size=0;FILE*f=open_memstream(&text,&size);if(!f)return NULL;
    int rc=robotron_parameter_inventory(f,ctx);if(fclose(f))rc=-1;
    if(rc){free(text);if(rc>=0||size)exit(3);return NULL;}return text;
}
'''
FAULT=r'''
    int parameter_field=FIELD_SELECTION;
    if(parameter_field>=0 && robotron_start_phase==1){
        int(*toggle)(unsigned)=dlsym(ctx->vvp_handle,"robotron_vvp_parameter_toggle");
        char*direct_before=robotron_parameter_text(ctx);if(!toggle||!direct_before)exit(2);
        if(toggle(parameter_field)!=1)exit(2);
        char*direct=robotron_parameter_text(ctx);char*changed=display_snapshot(ctx,api);
        if(toggle(parameter_field)!=1)exit(3);
        char*restored=display_snapshot(ctx,api);
        int direct_ok=parameter_field<7?(direct&&strcmp(direct_before,direct)!=0):direct==NULL;
        int changed_ok=changed&&strcmp(before,changed)!=0,rejected=changed==NULL;
        int equal=restored&&!strcmp(before,restored);
        if(changed)robotron_metadata_log(stderr,"VB_STAGE changed\n%s",changed);
        if(restored)robotron_metadata_log(stderr,"VB_STAGE restored\n%s",restored);
        robotron_metadata_log(stderr,"VB_PARAMETER_FAULT field=%d direct=%d changed=%d rejected=%d restored=%d\n",parameter_field,direct_ok,changed_ok,rejected,equal);
        free(direct_before);free(direct);free(before);free(changed);free(restored);
        exit(direct_ok&&equal&&(parameter_field<7?changed_ok:rejected)?2:3);
    }
'''


def fault_header(header):
    header='static char*robotron_parameter_text(struct ng_vvp*);\n'+PREVIOUS_HEADER(header)+'\n'+HELPER
    modes=''.join(' && strcmp(mode,"parameter-'+name+'-corrupt")' for name in FIELDS)
    header=once(header,'&& strcmp(mode,"scope-signal-scope-corrupt"))','&& strcmp(mode,"scope-signal-scope-corrupt")'+modes+')')
    selection=''.join('!strcmp(mode,"parameter-'+name+'-corrupt")?'+str(field)+':' for name,field in FIELDS.items())+'-1'
    return once(header,'    int all_signal_field=',FAULT.replace('FIELD_SELECTION',selection)+'\n    int all_signal_field=')


def build(source,vpi,vpi_header,out):
    try:
        base.parameter_header=fault_header;base.build(source,vpi,vpi_header,out)
    finally:base.parameter_header=PREVIOUS_HEADER
    p=out/'build.json';r=json.loads(p.read_text());r['sources'][str(Path(__file__).resolve())]=sha(Path(__file__))
    r['scope']='Ten native parameter field controls must change or refuse direct and complete snapshots, then restore the complete dense state before controlled termination. Compact encoding remains log-only. No full transient qualification.'
    p.write_text(json.dumps(r,indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('source','vpi','vpi-header','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();build(a.source,a.vpi,a.vpi_header,a.out)
