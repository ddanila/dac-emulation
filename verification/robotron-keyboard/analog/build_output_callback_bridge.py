#!/usr/bin/env python3
"""Link output value-change callback registrations to initialized bridge ports."""
import argparse,json,platform,subprocess
from pathlib import Path
from ttl7406_probe import sha
from build_private_sync_bridge import instrument,UPSTREAM
from build_private_sync_family_bridge import REGISTER,VPI_SOURCE
from build_port_identity_bridge import ports_header,ports_vpi
HERE=Path(__file__).resolve().parent

OUTPUT_FAULT=r'''
    int output_field = !strcmp(mode,"output-user-corrupt") ? 0 :
        !strcmp(mode,"output-object-corrupt") ? 1 :
        !strcmp(mode,"output-function-corrupt") ? 2 :
        !strcmp(mode,"output-link-corrupt") ? 3 : -1;
    if (output_field>=0 && info->vtime>=5e-6) {
        if (robotron_output_fault(output_field)!=1) exit(2);
        char *changed=display_snapshot(ctx,api);
        if (robotron_output_fault(output_field)!=1) exit(3);
        char *restored=display_snapshot(ctx,api);
        int rejected=changed==NULL;
        int equal=restored && !strcmp(before,restored);
        if (restored) fprintf(stderr,"VB_STAGE restored\n%s",restored);
        fprintf(stderr,"VB_OUTPUT_FAULT field=%d rejected=%d restored=%d\n",output_field,rejected,equal);
        free(before);free(changed);free(restored);
        exit(rejected && equal ? 2 : 3);
    }
'''


def output_header(header):
    header=ports_header(header,(HERE/'fixtures/port_identity_bridge.h').read_text()+'\n'+(HERE/'fixtures/output_callback_bridge.h').read_text())
    replacements={
        'robotron_ports_inventory(f, ctx) || fprintf(f, "VA_END\\n")':'robotron_ports_inventory(f, ctx) || robotron_output_inventory(f, ctx) || fprintf(f, "VA_END\\n")',
        '&& strcmp(mode,"port-value-corrupt"))':'&& strcmp(mode,"port-value-corrupt") && strcmp(mode,"output-user-corrupt") && strcmp(mode,"output-object-corrupt") && strcmp(mode,"output-function-corrupt") && strcmp(mode,"output-link-corrupt"))',
        '    if ((!strcmp(mode,"port-handle-corrupt")':OUTPUT_FAULT+'\n    if ((!strcmp(mode,"port-handle-corrupt")'}
    for old,new in replacements.items():
        if header.count(old)!=1:raise ValueError('Changed initialized port boundary')
        header=header.replace(old,new)
    return header


def output_vpi(source):
    source=ports_vpi(source);old='    vpi_register_cb(&cb);'
    if source.count(old)!=1:raise ValueError('Changed watch registration')
    return source.replace(old,'''    extern void Robotron_output_registration(void*, vpiHandle, PLI_INT32(*)(struct t_cb_data*), vpiHandle);
    vpiHandle registered = vpi_register_cb(&cb);
    Robotron_output_registration(pp, registered, output_cb, handle);''')


def build(source,vpi,vpi_header,out):
    source=source.resolve();vpi=vpi.resolve();vpi_header=vpi_header.resolve();out=out.resolve()
    verilog=source/'src/xspice/verilog';upstream=verilog/'icarus_shim.c'
    if platform.system()=='Windows':raise ValueError('Requires reviewed pthread bridge')
    if sha(upstream)!=UPSTREAM or sha(vpi)!=VPI_SOURCE:raise ValueError('Changed pinned bridge/VPI sources')
    out.mkdir(exist_ok=False);(out/'include/ngspice').mkdir(parents=True)
    (out/'include/ngspice/config.h').write_text('/* Standalone bridge: explicit runtime paths. */\n')
    header=HERE/'fixtures/display_board_bridge.h'
    (out/'icarus_shim.c').write_text(instrument(upstream.read_text(),REGISTER+'\n'+output_header(header.read_text())))
    (out/'vpi.c').write_text(output_vpi(vpi.read_text()))
    includes=['-I'+str(out/'include'),'-I'+str(source/'src/include'),'-I'+str(verilog),'-I'+str(vpi_header.parent)]
    commands=[]
    for src,name in [('icarus_shim.c','ivlng.so'),('vpi.c','ivlng.vpi')]:
        flags=(['-dynamiclib'] if name.endswith('.so') else ['-bundle'])+['-undefined','dynamic_lookup'] if platform.system()=='Darwin' else ['-shared']
        command=['cc','-fPIC','-fvisibility=default',*includes,*flags,str(out/src),'-o',str(out/name)]
        subprocess.run(command,check=True);commands.append(command)
    dependencies=[Path(__file__),HERE/'build_port_identity_bridge.py',HERE/'fixtures/output_callback_bridge.h',HERE/'build_private_sync_bridge.py',HERE/'build_private_sync_family_bridge.py',HERE/'build_display_stop_bridge.py',HERE/'build_executing_wrapper_bridge.py',HERE/'fixtures/port_identity_bridge.h',header,upstream,vpi,vpi_header,
                  verilog/'icarus_shim.h',verilog/'coroutine_shim.h',verilog/'coroutine_cosim.h',
                  source/'src/include/ngspice/cmtypes.h',source/'src/include/ngspice/cosim.h']
    receipt={'qualified':False,'commands':commands,'sources':{str(p):sha(p) for p in dependencies},
             'outputs':{n:sha(out/n) for n in ('icarus_shim.c','vpi.c','ivlng.so','ivlng.vpi')},
             'scope':'Explicit watch-registration identities captured before port metadata initialization, then validated at paused boundaries with live callback lifetime/function/signal/user/list checks. Temporary value union is not observed. Board controls and general rollback remain open.'}
    (out/'build.json').write_text(json.dumps(receipt,indent=2)+'\n');print(out/'build.json')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('source','vpi','vpi-header','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();build(a.source,a.vpi,a.vpi_header,a.out)
