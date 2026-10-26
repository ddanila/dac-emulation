#!/usr/bin/env python3
"""Extend the paused display observer with a safe live stop-handle relationship."""
import argparse,json,platform,subprocess
from pathlib import Path
from ttl7406_probe import sha
from build_private_sync_bridge import instrument,UPSTREAM
from build_private_sync_family_bridge import REGISTER,identity_vpi,VPI_SOURCE
HERE=Path(__file__).resolve().parent
STOP=r'''
/* A saved stop handle is opaque. The runtime compares it against its live
 * registry before checking the known function/context; no stale dereference. */
static int display_stop_link(FILE *f, struct ng_vvp *ctx, struct display_board_api api)
{
    unsigned long long id = 0;
    if (ctx->stop_cb) {
        id = api.lookup(ctx->stop_cb, robotron_stop_function, (char*)ctx);
        if (!id) return -1;
    }
    return fprintf(f, "VR_BEGIN 1 %d %llu\nVR_END\n", ctx->stop_cb != NULL, id) < 0 ? -1 : 0;
}
'''
FAULT=r'''
    if (!strcmp(mode, "stop-corrupt") && info->vtime >= 5e-6 && ctx->stop_cb) {
        struct __vpiHandle *saved = ctx->stop_cb;
        ctx->stop_cb = (struct __vpiHandle*)(uintptr_t)1;
        char *changed = display_snapshot(ctx, api);
        ctx->stop_cb = saved;
        char *restored = display_snapshot(ctx, api);
        int rejected = changed == NULL;
        int equal = restored && !strcmp(before, restored);
        if (restored) fprintf(stderr, "VB_STAGE restored\n%s", restored);
        fprintf(stderr, "VB_STOP_FAULT rejected=%d restored=%d\n", rejected, equal);
        free(before); free(changed); free(restored);
        exit(rejected && equal ? 2 : 3);
    }
'''


def stop_header(header):
    replacements={
        'static char *display_snapshot(':STOP+'\nstatic char *display_snapshot(',
        'api.association(f, api.lookup) || fprintf(f, "VA_END\\n") < 0;':'api.association(f, api.lookup) || display_stop_link(f, ctx, api) || fprintf(f, "VA_END\\n") < 0;',
        'if (strcmp(mode, "observe") && strcmp(mode, "corrupt")) {':'if (strcmp(mode, "observe") && strcmp(mode, "corrupt") && strcmp(mode, "stop-corrupt")) {',
        '    if (!strcmp(mode, "corrupt") && info->vtime >= 5e-6) {':FAULT+'\n    if (!strcmp(mode, "corrupt") && info->vtime >= 5e-6) {'}
    for before,after in replacements.items():
        if header.count(before)!=1:raise ValueError('Changed display observer boundary')
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
    (out/'icarus_shim.c').write_text(instrument(upstream.read_text(),REGISTER+'\n'+stop_header(header.read_text())))
    (out/'vpi.c').write_text(identity_vpi(vpi.read_text()))
    includes=['-I'+str(out/'include'),'-I'+str(source/'src/include'),'-I'+str(verilog),'-I'+str(vpi_header.parent)]
    commands=[]
    for src,name in [('icarus_shim.c','ivlng.so'),('vpi.c','ivlng.vpi')]:
        flags=(['-dynamiclib'] if name.endswith('.so') else ['-bundle'])+['-undefined','dynamic_lookup'] if platform.system()=='Darwin' else ['-shared']
        command=['cc','-fPIC','-fvisibility=default',*includes,*flags,str(out/src),'-o',str(out/name)]
        subprocess.run(command,check=True);commands.append(command)
    dependencies=[Path(__file__),HERE/'build_private_sync_bridge.py',HERE/'build_private_sync_family_bridge.py',header,upstream,vpi,vpi_header,
                  verilog/'icarus_shim.h',verilog/'coroutine_shim.h',verilog/'coroutine_cosim.h',
                  source/'src/include/ngspice/cmtypes.h',source/'src/include/ngspice/cosim.h']
    receipt={'qualified':False,'commands':commands,'sources':{str(p):sha(p) for p in dependencies},
             'outputs':{n:sha(out/n) for n in ('icarus_shim.c','vpi.c','ivlng.so','ivlng.vpi')},
             'scope':'Paused typed display observation plus saved stop-handle lookup against the live callback registry and known function/context. Invalid-handle fault restored before scheduling. Requires matched board controls; wrapper, port referents and freed storage remain open.'}
    (out/'build.json').write_text(json.dumps(receipt,indent=2)+'\n');print(out/'build.json')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('source','vpi','vpi-header','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();build(a.source,a.vpi,a.vpi_header,a.out)
