#!/usr/bin/env python3
"""Inject isolated parameter faults into complete native board snapshots."""
import argparse,json
from pathlib import Path
import build_memory_bridge as base
from build_startup_callback_bridge import once
from ttl7406_probe import sha
PREVIOUS_HEADER=base.memory_header
FIELDS={'name':0,'name-pointer':1,'cache-pointer':2,'port-head':3,'storage-pointer':4}
HELPER=r'''
static char*robotron_memory_probe(struct ng_vvp*ctx,int array)
{
    int(*fn)(FILE*)=dlsym(ctx->vvp_handle,array?"robotron_vvp_array_inventory":"robotron_vvp_memory_metadata_inventory");
    char*text=NULL;size_t size=0;FILE*f=open_memstream(&text,&size);if(!f||!fn)exit(3);
    int rc=fn(f);if(fclose(f))rc=-1;
    if(rc){free(text);if(rc>=0||size)exit(3);return NULL;}return text;
}
'''
FAULT=r'''
    int memory_field=FIELD_SELECTION;
    if(memory_field>=0 && robotron_start_phase==1){
        int(*toggle)(unsigned)=dlsym(ctx->vvp_handle,"robotron_vvp_memory_toggle");
        char*names_before=robotron_memory_probe(ctx,0);char*arrays_before=robotron_memory_probe(ctx,1);
        if(!toggle||!names_before||!arrays_before||toggle(memory_field)!=1)exit(2);
        char*names=robotron_memory_probe(ctx,0);char*arrays=robotron_memory_probe(ctx,1);char*changed=display_snapshot(ctx,api);
        if(toggle(memory_field)!=1)exit(3);
        char*restored=display_snapshot(ctx,api);
        int names_ok=memory_field==0?(names&&strcmp(names_before,names)!=0):memory_field==1?names==NULL:(names&&!strcmp(names_before,names));
        int arrays_ok=memory_field<2?(arrays&&!strcmp(arrays_before,arrays)):arrays==NULL;
        int changed_ok=changed&&strcmp(before,changed)!=0,rejected=changed==NULL;
        int equal=restored&&!strcmp(before,restored);
        if(changed)robotron_metadata_log(stderr,"VB_STAGE changed\n%s",changed);
        if(restored)robotron_metadata_log(stderr,"VB_STAGE restored\n%s",restored);
        robotron_metadata_log(stderr,"VB_MEMORY_FAULT field=%d direct=%d changed=%d rejected=%d restored=%d\n",memory_field,names_ok&&arrays_ok,changed_ok,rejected,equal);
        free(names_before);free(arrays_before);free(names);free(arrays);free(before);free(changed);free(restored);
        exit(names_ok&&arrays_ok&&equal&&(memory_field==0?changed_ok:rejected)?2:3);
    }
'''


def fault_header(header):
    header='static char*robotron_memory_probe(struct ng_vvp*,int);\n'+PREVIOUS_HEADER(header)+'\n'+HELPER
    modes=''.join(' && strcmp(mode,"memory-'+name+'-corrupt")' for name in FIELDS)
    header=once(header,'&& strcmp(mode,"parameter-name-pointer-corrupt"))','&& strcmp(mode,"parameter-name-pointer-corrupt")'+modes+')')
    selection=''.join('!strcmp(mode,"memory-'+name+'-corrupt")?'+str(field)+':' for name,field in FIELDS.items())+'-1'
    return once(header,'    int parameter_field=',FAULT.replace('FIELD_SELECTION',selection)+'\n    int parameter_field=')


def build(source,vpi,vpi_header,out):
    try:
        base.memory_header=fault_header;base.build(source,vpi,vpi_header,out)
    finally:base.memory_header=PREVIOUS_HEADER
    p=out/'build.json';r=json.loads(p.read_text());r['sources'][str(Path(__file__).resolve())]=sha(Path(__file__))
    r['scope']='Five native memory field controls must change or refuse direct and complete snapshots, then restore the complete dense state before controlled termination. Compact encoding remains log-only. No full transient qualification.'
    p.write_text(json.dumps(r,indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('source','vpi','vpi-header','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();build(a.source,a.vpi,a.vpi_header,a.out)
