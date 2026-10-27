#!/usr/bin/env python3
"""Add restored port payload faults to complete combined snapshots."""
import argparse,json
from pathlib import Path
import build_port_payload_bridge as base
from build_startup_callback_bridge import once
from ttl7406_probe import sha
PREVIOUS_HEADER=base.port_header
NAMES=('index', 'direction', 'bit-index', 'width', 'parent', 'name-pointer', 'net-reference', 'bit-parent', 'readiness')
HELPER=r'''
static char*robotron_port_payload_text(struct ng_vvp*ctx)
{
    char*text=NULL;size_t size=0;FILE*f=open_memstream(&text,&size);if(!f)return NULL;
    int rc=robotron_port_payload_inventory(f,ctx);if(fclose(f))rc=-1;
    if(rc){free(text);if(rc>=0||size)exit(3);return NULL;}return text;
}
'''
FAULT=r'''
    int port_field=FIELD_SELECTION;
    if(port_field>=0 && robotron_start_phase==1){
        int(*toggle)(unsigned)=dlsym(ctx->vvp_handle,"robotron_vvp_port_payload_toggle");
        char*direct_before=robotron_port_payload_text(ctx);if(!toggle||!direct_before)exit(2);
        if(toggle(port_field)!=1)exit(2);
        char*direct=robotron_port_payload_text(ctx);char*changed=display_snapshot(ctx,api);
        if(toggle(port_field)!=1)exit(3);
        char*restored=display_snapshot(ctx,api);
        int direct_ok=port_field<3?(direct&&strcmp(direct_before,direct)!=0):direct==NULL;
        int changed_ok=changed&&strcmp(before,changed)!=0,rejected=changed==NULL;
        int equal=restored&&!strcmp(before,restored);
        if(changed)robotron_metadata_log(stderr,"VB_STAGE changed\n%s",changed);
        if(restored)robotron_metadata_log(stderr,"VB_STAGE restored\n%s",restored);
        robotron_metadata_log(stderr,"VB_PORT_PAYLOAD_FAULT field=%d direct=%d changed=%d rejected=%d restored=%d\n",port_field,direct_ok,changed_ok,rejected,equal);
        free(direct_before);free(direct);free(before);free(changed);free(restored);
        exit(direct_ok&&equal&&(port_field<3?changed_ok:rejected)?2:3);
    }
'''


def fault_header(header):
    header='static char*robotron_port_payload_text(struct ng_vvp*);\n'+PREVIOUS_HEADER(header)+'\n'+HELPER
    modes=''.join(' && strcmp(mode,"port-payload-'+name+'-corrupt")' for name in NAMES)
    header=once(header,'&& strcmp(mode,"scope-metadata-intern-corrupt"))','&& strcmp(mode,"scope-metadata-intern-corrupt")'+modes+')')
    selection=''.join('!strcmp(mode,"port-payload-'+name+'-corrupt")?'+str(i)+':' for i,name in enumerate(NAMES))+'-1'
    return once(header,'    int metadata_field=',FAULT.replace('FIELD_SELECTION',selection)+'\n    int metadata_field=')


def build(source,vpi,vpi_header,out):
    try:
        base.port_header=fault_header;base.build(source,vpi,vpi_header,out)
    finally:base.port_header=PREVIOUS_HEADER
    p=out/'build.json';r=json.loads(p.read_text());r['sources'][str(Path(__file__).resolve())]=sha(Path(__file__))
    r['scope']='Combined native port field faults and malformed-field refusals. Direct metadata and complete dense state must detect faults and restore before termination. Compact encoding only at log output; normal transient qualification remains separate.'
    p.write_text(json.dumps(r,indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('source','vpi','vpi-header','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();build(a.source,a.vpi,a.vpi_header,a.out)
