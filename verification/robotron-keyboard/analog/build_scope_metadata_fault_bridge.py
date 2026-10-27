#!/usr/bin/env python3
"""Add restored scope metadata faults to complete combined snapshots."""
import argparse,json
from pathlib import Path
import build_scope_metadata_bridge as base
from build_startup_callback_bridge import once
from ttl7406_probe import sha
PREVIOUS_HEADER=base.metadata_header
NAMES=('units','line','function-type','function-width','function-init','intern')
HELPER=r'''
static char*robotron_scope_metadata_text(struct ng_vvp*ctx)
{
    char*text=NULL;size_t size=0;FILE*f=open_memstream(&text,&size);if(!f)return NULL;
    int rc=robotron_scope_metadata_inventory(f,ctx);if(fclose(f))rc=-1;
    if(rc){free(text);return NULL;}return text;
}
'''
FAULT=r'''
    int metadata_field=FIELD_SELECTION;
    if(metadata_field>=0 && robotron_start_phase==1){
        int(*toggle)(unsigned)=dlsym(ctx->vvp_handle,"robotron_vvp_scope_metadata_toggle");
        char*direct_before=robotron_scope_metadata_text(ctx);if(!toggle||!direct_before)exit(2);
        if(toggle(metadata_field)!=1)exit(2);
        char*direct=robotron_scope_metadata_text(ctx);char*changed=display_snapshot(ctx,api);
        if(toggle(metadata_field)!=1)exit(3);
        char*restored=display_snapshot(ctx,api);
        int direct_ok=metadata_field<5?(direct&&strcmp(direct_before,direct)!=0):direct==NULL;
        int changed_ok=changed&&strcmp(before,changed)!=0,rejected=changed==NULL;
        int equal=restored&&!strcmp(before,restored);
        if(changed)robotron_metadata_log(stderr,"VB_STAGE changed\n%s",changed);
        if(restored)robotron_metadata_log(stderr,"VB_STAGE restored\n%s",restored);
        robotron_metadata_log(stderr,"VB_SCOPE_METADATA_FAULT field=%d direct=%d changed=%d rejected=%d restored=%d\n",metadata_field,direct_ok,changed_ok,rejected,equal);
        free(direct_before);free(direct);free(before);free(changed);free(restored);
        exit(direct_ok&&equal&&(metadata_field<5?changed_ok:rejected)?2:3);
    }
'''


def fault_header(header):
    header='static char*robotron_scope_metadata_text(struct ng_vvp*);\n'+PREVIOUS_HEADER(header)+'\n'+HELPER
    modes=''.join(' && strcmp(mode,"scope-metadata-'+name+'-corrupt")' for name in NAMES)
    header=once(header,'&& strcmp(mode,"typed-signal-scope-corrupt"))','&& strcmp(mode,"typed-signal-scope-corrupt")'+modes+')')
    selection=''.join('!strcmp(mode,"scope-metadata-'+name+'-corrupt")?'+str(i)+':' for i,name in enumerate(NAMES))+'-1'
    return once(header,'    int typed_field=',FAULT.replace('FIELD_SELECTION',selection)+'\n    int typed_field=')


def build(source,vpi,vpi_header,out):
    try:
        base.metadata_header=fault_header;base.build(source,vpi,vpi_header,out)
    finally:base.metadata_header=PREVIOUS_HEADER
    p=out/'build.json';r=json.loads(p.read_text());r['sources'][str(Path(__file__).resolve())]=sha(Path(__file__))
    r['scope']='Combined scope metadata timescale/source/function faults and invalid intern refusal. Direct metadata and complete dense state must detect faults and restore before termination. Compact encoding only at log output; normal transient qualification remains separate.'
    p.write_text(json.dumps(r,indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('source','vpi','vpi-header','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();build(a.source,a.vpi,a.vpi_header,a.out)
