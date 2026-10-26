#!/usr/bin/env python3
"""Build a separate bridge/VPI pair with explicit stop-callback identity handoff."""
import argparse,json,platform,subprocess
from pathlib import Path
from ttl7406_probe import sha
from build_private_sync_bridge import instrument,UPSTREAM
HERE=Path(__file__).resolve().parent
VPI_SOURCE='54419fef0ac32cba3dc8e13790baabcede9e2bc9c26f55424d7ff8686f08215e'
REGISTER='''/* Single-instance identity handoff, completed on the HDL thread before
 * start_cb can yield to SPICE. Neither callback code nor data is guessed from
 * addresses, allocator contents or a possibly expired stop_cb handle. */
struct t_cb_data;
static struct ng_vvp *robotron_identity_context;
static int32_t (*robotron_stop_function)(struct t_cb_data*);
void Robotron_sync_identity(struct ng_vvp *ctx, int32_t (*function)(struct t_cb_data*))
{
    if (!ctx || !function || robotron_identity_context || robotron_stop_function) {
        fprintf(stderr, "Invalid synchronization callback identity handoff\\n"); exit(2);
    }
    robotron_identity_context = ctx;
    robotron_stop_function = function;
}
'''


def identity_header(header):
    old='observe(stream, (char*)ctx, NULL)'
    marker='    char *text = NULL;'
    if header.count(old)!=1 or header.count(marker)!=1:raise ValueError('Changed callback observer header')
    header=header.replace(old,'observe(stream, (char*)ctx, robotron_stop_function)')
    header=header.replace('    struct t_cb_data;\n','')
    header=header.replace(marker,'''    if (ctx != robotron_identity_context || !robotron_stop_function) {
        fprintf(stderr, "Missing synchronization callback identity handoff\\n"); exit(2);
    }
'''+marker)
    start=header.index('static char *private_sync_snapshot')
    return REGISTER+'\n'+header[start:]


def identity_vpi(source):
    marker='    cbd.user_data = (PLI_BYTE8 *)Get_ng_vvp();\n    vpi_register_cb(&cbd);'
    if source.count(marker)!=1:raise ValueError('Changed VPI startup registration')
    replacement='''    extern void Robotron_sync_identity(struct ng_vvp*, PLI_INT32(*)(struct t_cb_data*));
    cbd.user_data = (PLI_BYTE8 *)Get_ng_vvp();
    Robotron_sync_identity((struct ng_vvp*)cbd.user_data, next_advance_cb);
    vpi_register_cb(&cbd);'''
    return source.replace(marker,replacement)


def build(source,vpi,vpi_header,out):
    source=source.resolve();vpi=vpi.resolve();vpi_header=vpi_header.resolve();out=out.resolve()
    verilog=source/'src/xspice/verilog';upstream=verilog/'icarus_shim.c'
    if platform.system()=='Windows':raise ValueError('Requires reviewed pthread bridge')
    if sha(upstream)!=UPSTREAM or sha(vpi)!=VPI_SOURCE:raise ValueError('Changed pinned bridge/VPI sources')
    out.mkdir(exist_ok=False);(out/'include/ngspice').mkdir(parents=True)
    (out/'include/ngspice/config.h').write_text('/* Standalone bridge: explicit runtime paths. */\n')
    header=HERE/'fixtures/private_sync_bridge.h'
    (out/'icarus_shim.c').write_text(instrument(upstream.read_text(),identity_header(header.read_text())))
    (out/'vpi.c').write_text(identity_vpi(vpi.read_text()))
    includes=['-I'+str(out/'include'),'-I'+str(source/'src/include'),'-I'+str(verilog),'-I'+str(vpi_header.parent)]
    commands=[]
    for src,name in [('icarus_shim.c','ivlng.so'),('vpi.c','ivlng.vpi')]:
        flags=(['-dynamiclib'] if name.endswith('.so') else ['-bundle'])+['-undefined','dynamic_lookup'] if platform.system()=='Darwin' else ['-shared']
        command=['cc','-fPIC','-fvisibility=default',*includes,*flags,str(out/src),'-o',str(out/name)]
        subprocess.run(command,check=True);commands.append(command)
    dependencies=[Path(__file__),HERE/'build_private_sync_bridge.py',header,upstream,vpi,vpi_header,
                  verilog/'icarus_shim.h',verilog/'coroutine_shim.h',verilog/'coroutine_cosim.h',
                  source/'src/include/ngspice/cmtypes.h',source/'src/include/ngspice/cosim.h']
    receipt={'qualified':False,'commands':commands,'sources':{str(p):sha(p) for p in dependencies},
             'outputs':{n:sha(out/n) for n in ('icarus_shim.c','vpi.c','ivlng.so','ivlng.vpi')},
             'scope':'Single-instance explicit next_advance_cb identity handoff. Requires matched board controls; referenced data, initial start callback, executing stack and general rollback remain unqualified.'}
    (out/'build.json').write_text(json.dumps(receipt,indent=2)+'\n');print(out/'build.json')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('source','vpi','vpi-header','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();build(a.source,a.vpi,a.vpi_header,a.out)
