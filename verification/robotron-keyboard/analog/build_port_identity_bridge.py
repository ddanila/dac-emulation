#!/usr/bin/env python3
"""Bind initialized bridge ports to their VPI handles and owning context."""
import argparse,json,platform,subprocess
from pathlib import Path
from ttl7406_probe import sha
from build_private_sync_bridge import instrument,UPSTREAM
from build_private_sync_family_bridge import REGISTER,identity_vpi,VPI_SOURCE
HERE=Path(__file__).resolve().parent
from build_executing_wrapper_bridge import wrapper_header

PORT_FAULT=r'''
    if ((!strcmp(mode,"port-handle-corrupt") || !strcmp(mode,"port-context-corrupt") ||
         !strcmp(mode,"port-value-corrupt")) && info->vtime >= 5e-6) {
        struct ngvp_port *port=ctx->ports;
        struct __vpiHandle *saved_handle=port->handle;
        struct ng_vvp *saved_context=port->ctx;
        int32_t saved_value=port->previous.aval;
        int value_fault=!strcmp(mode,"port-value-corrupt");
        if (!strcmp(mode,"port-handle-corrupt")) port->handle=(struct __vpiHandle*)(uintptr_t)1;
        else if (!strcmp(mode,"port-context-corrupt")) port->ctx=NULL;
        else port->previous.aval ^= 1;
        char *changed=display_snapshot(ctx,api);
        port->handle=saved_handle; port->ctx=saved_context; port->previous.aval=saved_value;
        char *restored=display_snapshot(ctx,api);
        int detected=value_fault ? (changed && strcmp(before,changed)) : changed==NULL;
        int equal=restored && !strcmp(before,restored);
        if (changed) fprintf(stderr,"VB_STAGE changed\n%s",changed);
        if (restored) fprintf(stderr,"VB_STAGE restored\n%s",restored);
        fprintf(stderr,"VB_PORT_FAULT kind=%s detected=%d restored=%d\n",mode,!!detected,equal);
        free(before); free(changed); free(restored);
        exit(detected && equal ? 2 : 3);
    }
'''


def ports_header(header,ports):
    header=wrapper_header(header)
    changes={
        'static char *display_snapshot(':ports+'\nstatic char *display_snapshot(',
        'api.executing(f) || fprintf(f, "VA_END\\n")':'api.executing(f) || robotron_ports_inventory(f, ctx) || fprintf(f, "VA_END\\n")',
        '&& strcmp(mode, "wrapper-corrupt"))':'&& strcmp(mode, "wrapper-corrupt") && strcmp(mode,"port-handle-corrupt") && strcmp(mode,"port-context-corrupt") && strcmp(mode,"port-value-corrupt"))',
        '    if (!strcmp(mode, "wrapper-corrupt") && info->vtime >= 5e-6) {':PORT_FAULT+'\n    if (!strcmp(mode, "wrapper-corrupt") && info->vtime >= 5e-6) {'}
    for before,after in changes.items():
        if header.count(before)!=1:raise ValueError('Changed wrapper boundary')
        header=header.replace(before,after)
    return header


def ports_vpi(source):
    source=identity_vpi(source)
    marker='    /* Make a direct call to the "end-of-advance" callback to start running. */'
    if source.count(marker)!=1:raise ValueError('Changed VPI port initialization boundary')
    return source.replace(marker,'''    extern void Robotron_ports_identity(struct ng_vvp*, char*(*)(PLI_INT32,vpiHandle), PLI_INT32);
    Robotron_ports_identity(ctx, vpi_get_str, vpiFullName);

'''+marker)


def build(source,vpi,vpi_header,out):
    source=source.resolve();vpi=vpi.resolve();vpi_header=vpi_header.resolve();out=out.resolve()
    verilog=source/'src/xspice/verilog';upstream=verilog/'icarus_shim.c'
    if platform.system()=='Windows':raise ValueError('Requires reviewed pthread bridge')
    if sha(upstream)!=UPSTREAM or sha(vpi)!=VPI_SOURCE:raise ValueError('Changed pinned bridge/VPI sources')
    out.mkdir(exist_ok=False);(out/'include/ngspice').mkdir(parents=True)
    (out/'include/ngspice/config.h').write_text('/* Standalone bridge: explicit runtime paths. */\n')
    header=HERE/'fixtures/display_board_bridge.h'
    (out/'icarus_shim.c').write_text(instrument(upstream.read_text(),REGISTER+'\n'+ports_header(header.read_text(),(HERE/'fixtures/port_identity_bridge.h').read_text())))
    (out/'vpi.c').write_text(ports_vpi(vpi.read_text()))
    includes=['-I'+str(out/'include'),'-I'+str(source/'src/include'),'-I'+str(verilog),'-I'+str(vpi_header.parent)]
    commands=[]
    for src,name in [('icarus_shim.c','ivlng.so'),('vpi.c','ivlng.vpi')]:
        flags=(['-dynamiclib'] if name.endswith('.so') else ['-bundle'])+['-undefined','dynamic_lookup'] if platform.system()=='Darwin' else ['-shared']
        command=['cc','-fPIC','-fvisibility=default',*includes,*flags,str(out/src),'-o',str(out/name)]
        subprocess.run(command,check=True);commands.append(command)
    dependencies=[Path(__file__),HERE/'build_private_sync_bridge.py',HERE/'build_private_sync_family_bridge.py',HERE/'build_display_stop_bridge.py',HERE/'build_executing_wrapper_bridge.py',HERE/'fixtures/port_identity_bridge.h',header,upstream,vpi,vpi_header,
                  verilog/'icarus_shim.h',verilog/'coroutine_shim.h',verilog/'coroutine_cosim.h',
                  source/'src/include/ngspice/cmtypes.h',source/'src/include/ngspice/cosim.h']
    receipt={'qualified':False,'commands':commands,'sources':{str(p):sha(p) for p in dependencies},
             'outputs':{n:sha(out/n) for n in ('icarus_shim.c','vpi.c','ivlng.so','ivlng.vpi')},
             'scope':'Initialized port state and explicit array/handle/context identities bound before the first HDL yield. Input-only new values are not read. Requires matched board controls; callback registration roots, initialization families and freed storage remain open.'}
    (out/'build.json').write_text(json.dumps(receipt,indent=2)+'\n');print(out/'build.json')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('source','vpi','vpi-header','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();build(a.source,a.vpi,a.vpi_header,a.out)
