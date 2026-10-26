#!/usr/bin/env python3
"""Integrate executing generic-wrapper observation into the paused board bridge."""
import argparse,json,platform,subprocess
from pathlib import Path
from ttl7406_probe import sha
from build_private_sync_bridge import instrument,UPSTREAM
from build_private_sync_family_bridge import REGISTER,identity_vpi,VPI_SOURCE
HERE=Path(__file__).resolve().parent
from build_display_stop_bridge import stop_header

WRAPPER_FAULT=r'''
    if (!strcmp(mode, "wrapper-corrupt") && info->vtime >= 5e-6) {
        int changed = api.toggle_delete();
        if (changed != 0 && changed != 1) exit(2);
        if (changed) {
            char *after = display_snapshot(ctx, api);
            if (api.toggle_delete() != 1) exit(3);
            char *restored = display_snapshot(ctx, api);
            int detected = after && strcmp(before, after);
            int equal = restored && !strcmp(before, restored);
            if (after) fprintf(stderr, "VB_STAGE changed\n%s", after);
            if (restored) fprintf(stderr, "VB_STAGE restored\n%s", restored);
            fprintf(stderr, "VB_WRAPPER_FAULT detected=%d restored=%d\n", !!detected, equal);
            free(before); free(after); free(restored);
            exit(detected && equal ? 2 : 3);
        }
    }
'''


def wrapper_header(header):
    header=stop_header(header)
    replacements={
        '    display_null_fn toggle;':'    display_null_fn toggle;\n    int (*executing)(FILE*);\n    int (*toggle_delete)(void);',
        '    api.payload = dlsym(module, "robotron_display_inventory");':'    api.executing = dlsym(ctx->vvp_handle, "robotron_vvp_executing_inventory");\n    api.toggle_delete = dlsym(ctx->vvp_handle, "robotron_vvp_executing_toggle_delete");\n    api.payload = dlsym(module, "robotron_display_inventory");',
        '!api.association || !api.mutate)':'!api.association || !api.mutate || !api.executing || !api.toggle_delete)',
        'display_stop_link(f, ctx, api) || fprintf(f, "VA_END\\n")':'display_stop_link(f, ctx, api) || api.executing(f) || fprintf(f, "VA_END\\n")',
        '&& strcmp(mode, "stop-corrupt"))':'&& strcmp(mode, "stop-corrupt") && strcmp(mode, "wrapper-corrupt"))',
        '    if (!strcmp(mode, "stop-corrupt") && info->vtime >= 5e-6 && ctx->stop_cb) {':WRAPPER_FAULT+'\n    if (!strcmp(mode, "stop-corrupt") && info->vtime >= 5e-6 && ctx->stop_cb) {'}
    for before,after in replacements.items():
        if header.count(before)!=1:raise ValueError('Changed stop/display observer boundary')
        header=header.replace(before,after)
    return header


def build(source,vpi,vpi_header,out):
    source=source.resolve();vpi=vpi.resolve();vpi_header=vpi_header.resolve();out=out.resolve()
    verilog=source/'src/xspice/verilog';upstream=verilog/'icarus_shim.c'
    if platform.system()=='Windows':raise ValueError('Requires reviewed pthread bridge')
    if sha(upstream)!=UPSTREAM or sha(vpi)!=VPI_SOURCE:raise ValueError('Changed pinned bridge/VPI sources')
    out.mkdir(exist_ok=False);(out/'include/ngspice').mkdir(parents=True)
    (out/'include/ngspice/config.h').write_text('/* Standalone bridge: explicit runtime paths. */\n')
    header=HERE/'fixtures/display_board_bridge.h'
    (out/'icarus_shim.c').write_text(instrument(upstream.read_text(),REGISTER+'\n'+wrapper_header(header.read_text())))
    (out/'vpi.c').write_text(identity_vpi(vpi.read_text()))
    includes=['-I'+str(out/'include'),'-I'+str(source/'src/include'),'-I'+str(verilog),'-I'+str(vpi_header.parent)]
    commands=[]
    for src,name in [('icarus_shim.c','ivlng.so'),('vpi.c','ivlng.vpi')]:
        flags=(['-dynamiclib'] if name.endswith('.so') else ['-bundle'])+['-undefined','dynamic_lookup'] if platform.system()=='Darwin' else ['-shared']
        command=['cc','-fPIC','-fvisibility=default',*includes,*flags,str(out/src),'-o',str(out/name)]
        subprocess.run(command,check=True);commands.append(command)
    dependencies=[Path(__file__),HERE/'build_private_sync_bridge.py',HERE/'build_private_sync_family_bridge.py',HERE/'build_display_stop_bridge.py',header,upstream,vpi,vpi_header,
                  verilog/'icarus_shim.h',verilog/'coroutine_shim.h',verilog/'coroutine_cosim.h',
                  source/'src/include/ngspice/cmtypes.h',source/'src/include/ngspice/cosim.h']
    receipt={'qualified':False,'commands':commands,'sources':{str(p):sha(p) for p in dependencies},
             'outputs':{n:sha(out/n) for n in ('icarus_shim.c','vpi.c','ivlng.so','ivlng.vpi')},
             'scope':'Paused display and stop relationships plus executing generic-wrapper identity and deletion ownership. Requires matched board controls; other referents, initialization families, scheduler continuation and freed storage remain open.'}
    (out/'build.json').write_text(json.dumps(receipt,indent=2)+'\n');print(out/'build.json')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('source','vpi','vpi-header','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();build(a.source,a.vpi,a.vpi_header,a.out)
